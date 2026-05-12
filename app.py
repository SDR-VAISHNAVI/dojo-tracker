from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import date
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = "postgresql://postgres.losiamfhydgdsojghcui:VaishnaviGiri@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

BELT_ORDER = [
    'White', 'Yellow', 'Orange', 'Green', 'Blue',
    'Purple 1', 'Purple 2', 'Brown 1', 'Brown 2', 'Black'
]

MONTH_NAMES = ['','January','February','March','April','May','June',
               'July','August','September','October','November','December']

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def next_belt(current):
    """Return the next belt level, or same if already Black."""
    clean = (current or '').lower().replace(' belt','').strip()
    try:
        idx = next(i for i, b in enumerate(BELT_ORDER) if b.lower() == clean)
        return BELT_ORDER[min(idx + 1, len(BELT_ORDER) - 1)]
    except StopIteration:
        return current


# ==============================
# DOJOS
# ==============================

@app.route('/api/dojos', strict_slashes=False)
def get_dojos():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, name FROM dojos ORDER BY name")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# BATCHES
# ==============================

@app.route('/api/batches', strict_slashes=False)
def get_batches():
    dojo_id = request.args.get('dojo_id')
    if not dojo_id:
        return jsonify({"error": "dojo_id is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name FROM batches
            WHERE dojo_id = %s ORDER BY name
        """, (dojo_id,))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# STUDENTS
# ==============================

@app.route('/api/students', strict_slashes=False)
def get_students():
    batch_id = request.args.get('batch_id')
    dojo_id  = request.args.get('dojo_id')
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if batch_id:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, s.batch_id,
                       s.phone_number, b.dojo_id, b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE s.batch_id = %s ORDER BY s.name
            """, (batch_id,))
        elif dojo_id:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, s.batch_id,
                       s.phone_number, b.dojo_id, b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE b.dojo_id = %s ORDER BY s.name
            """, (dojo_id,))
        else:
            return jsonify({"error": "batch_id or dojo_id is required"}), 400
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students/stats', strict_slashes=False)
def student_stats():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) AS total FROM students")
        total = cur.fetchone()['total']
        cur.execute("SELECT COUNT(*) AS black FROM students WHERE LOWER(belt_level) LIKE '%black%'")
        black = cur.fetchone()['black']
        cur.execute("SELECT COUNT(*) AS batches FROM batches")
        batches = cur.fetchone()['batches']
        return jsonify({"total": total, "black": black, "batches": batches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# STUDENT PROFILE
# Full history: attendance + fees + stats
# ==============================

@app.route('/api/students/<int:student_id>/profile', strict_slashes=False)
def student_profile(student_id):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Basic info
        cur.execute("""
            SELECT s.id, s.name, s.belt_level, s.phone_number,
                   b.name AS batch_name, b.id AS batch_id,
                   d.name AS dojo_name, d.id AS dojo_id
            FROM students s
            JOIN batches b ON s.batch_id = b.id
            JOIN dojos d ON b.dojo_id = d.id
            WHERE s.id = %s
        """, (student_id,))
        student = cur.fetchone()
        if not student:
            return jsonify({"error": "Student not found"}), 404

        # Attendance history (all records, newest first)
        cur.execute("""
            SELECT date, status
            FROM attendance
            WHERE student_id = %s
            ORDER BY date DESC
            LIMIT 100
        """, (student_id,))
        attendance_records = cur.fetchall()

        # Attendance stats
        cur.execute("""
            SELECT
                COUNT(*) AS total_classes,
                SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status='absent'  THEN 1 ELSE 0 END) AS total_absent
            FROM attendance
            WHERE student_id = %s
        """, (student_id,))
        att_stats = cur.fetchone()

        # Monthly attendance breakdown (last 6 months)
        cur.execute("""
            SELECT
                EXTRACT(YEAR FROM date)::int  AS year,
                EXTRACT(MONTH FROM date)::int AS month,
                SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present,
                SUM(CASE WHEN status='absent'  THEN 1 ELSE 0 END) AS absent,
                COUNT(*) AS total
            FROM attendance
            WHERE student_id = %s
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT 6
        """, (student_id,))
        monthly_att = cur.fetchall()

        # Fee history (last 12 months)
        cur.execute("""
            SELECT month, year, status
            FROM fees
            WHERE student_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 12
        """, (student_id,))
        fee_records = cur.fetchall()

        total    = att_stats['total_classes'] or 0
        present  = att_stats['total_present'] or 0
        absent   = att_stats['total_absent']  or 0
        pct      = round(present / total * 100, 1) if total else 0

        return jsonify({
            "student": dict(student),
            "attendance": {
                "records": [dict(r) for r in attendance_records],
                "stats": {
                    "total": total,
                    "present": present,
                    "absent": absent,
                    "percentage": pct
                },
                "monthly": [dict(r) for r in monthly_att]
            },
            "fees": [dict(r) for r in fee_records]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students', methods=['POST'], strict_slashes=False)
def add_student():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    name         = (data.get('name') or '').strip()
    batch_id     = data.get('batch_id')
    belt         = (data.get('belt_level') or 'White').strip()
    phone_number = (data.get('phone_number') or '').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not batch_id:
        return jsonify({"error": "batch_id is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO students (name, batch_id, belt_level, phone_number)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (name, batch_id, belt, phone_number or None))
        student_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"success": True, "id": student_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students/<int:student_id>', methods=['PUT'], strict_slashes=False)
def update_student(student_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    name         = (data.get('name') or '').strip()
    batch_id     = data.get('batch_id')
    belt         = (data.get('belt_level') or 'White').strip()
    phone_number = (data.get('phone_number') or '').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not batch_id:
        return jsonify({"error": "batch_id is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE students SET name=%s, batch_id=%s, belt_level=%s, phone_number=%s
            WHERE id=%s
        """, (name, batch_id, belt, phone_number or None, student_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students/<int:student_id>', methods=['DELETE'], strict_slashes=False)
def delete_student(student_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM attendance WHERE student_id=%s", (student_id,))
        cur.execute("DELETE FROM fees WHERE student_id=%s", (student_id,))
        cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# ATTENDANCE
# ==============================

@app.route('/api/attendance', methods=['POST'], strict_slashes=False)
def mark_attendance():
    body = request.get_json()
    if not body or 'records' not in body:
        return jsonify({"error": "Missing records"}), 400
    records = body['records']
    if not records:
        return jsonify({"error": "records list is empty"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor()
        for r in records:
            att_date = r.get('date') or date.today().isoformat()
            cur.execute("""
                INSERT INTO attendance (student_id, status, date)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (student_id, date)
                DO UPDATE SET status = EXCLUDED.status
            """, (r['student_id'], r['status'], att_date))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# NO-ABSENCES MONTHLY REPORT
# ==============================

@app.route('/api/attendance/no-absences', strict_slashes=False)
def no_absences():
    dojo_id  = request.args.get('dojo_id')
    month    = request.args.get('month')
    year     = request.args.get('year')
    batch_id = request.args.get('batch_id')

    if not dojo_id or not month or not year:
        return jsonify({"error": "dojo_id, month, year are required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if dojo_id == 'all':
            if batch_id:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name, b.id AS batch_id
                    FROM students s
                    JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d   ON b.dojo_id  = d.id
                    WHERE s.batch_id = %s
                    ORDER BY d.name, b.name, s.name
                """, (batch_id,))
            else:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name, b.id AS batch_id
                    FROM students s
                    JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d   ON b.dojo_id  = d.id
                    ORDER BY d.name, b.name, s.name
                """)
        else:
            if batch_id:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name, b.id AS batch_id
                    FROM students s
                    JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d   ON b.dojo_id  = d.id
                    WHERE b.dojo_id = %s AND s.batch_id = %s
                    ORDER BY b.name, s.name
                """, (dojo_id, batch_id))
            else:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name, b.id AS batch_id
                    FROM students s
                    JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d   ON b.dojo_id  = d.id
                    WHERE b.dojo_id = %s
                    ORDER BY b.name, s.name
                """, (dojo_id,))

        all_students = cur.fetchall()
        if not all_students:
            return jsonify({"no_absence_students": [], "had_absence_students": [], "total_students": 0})

        student_ids = [s['id'] for s in all_students]

        cur.execute("""
            SELECT DISTINCT student_id FROM attendance
            WHERE student_id = ANY(%s) AND status = 'absent'
              AND EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s
        """, (student_ids, int(month), int(year)))
        had_absence_ids = {r['student_id'] for r in cur.fetchall()}

        cur.execute("""
            SELECT DISTINCT student_id FROM attendance
            WHERE student_id = ANY(%s)
              AND EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s
        """, (student_ids, int(month), int(year)))
        has_any_record_ids = {r['student_id'] for r in cur.fetchall()}

        no_absence = []
        had_absence = []
        for s in all_students:
            sid = s['id']
            if sid in had_absence_ids:
                had_absence.append(dict(s))
            elif sid in has_any_record_ids:
                no_absence.append(dict(s))

        return jsonify({
            "no_absence_students":  no_absence,
            "had_absence_students": had_absence,
            "total_students":       len(all_students)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# DAILY REPORT
# ==============================

@app.route('/api/reports', strict_slashes=False)
def get_report():
    batch_id = request.args.get('batch_id')
    att_date = request.args.get('date')
    if not batch_id:
        return jsonify({"error": "batch_id is required"}), 400
    if not att_date:
        return jsonify({"error": "date is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT s.id, s.name, s.belt_level, b.name AS batch_name
            FROM students s JOIN batches b ON s.batch_id = b.id
            WHERE s.batch_id = %s ORDER BY s.name
        """, (batch_id,))
        students_list = cur.fetchall()
        if not students_list:
            return jsonify({"students": [], "summary": {"total":0,"present":0,"absent":0,"unmarked":0,"percent":0}})
        cur.execute("""
            SELECT a.student_id, a.status FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.date = %s AND s.batch_id = %s
        """, (att_date, batch_id))
        att_map = {r['student_id']: r['status'] for r in cur.fetchall()}
        result = [{"id": s["id"], "name": s["name"], "belt_level": s["belt_level"],
                   "batch_name": s.get("batch_name",""), "status": att_map.get(s["id"])}
                  for s in students_list]
        total   = len(result)
        present = sum(1 for r in result if r["status"] == "present")
        absent  = sum(1 for r in result if r["status"] == "absent")
        unmarked= sum(1 for r in result if r["status"] is None)
        percent = round(present / total * 100, 1) if total else 0
        return jsonify({"students": result, "summary": {
            "total": total, "present": present, "absent": absent,
            "unmarked": unmarked, "percent": percent
        }})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# FEES
# ==============================

@app.route('/api/fees', strict_slashes=False)
def get_fees():
    dojo_id = request.args.get('dojo_id')
    month   = request.args.get('month')
    year    = request.args.get('year')
    if not dojo_id or not month or not year:
        return jsonify({"error": "dojo_id, month, year are required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT s.id, s.name, s.belt_level,
                   b.id AS batch_id, b.name AS batch_name,
                   COALESCE(f.status, 'unpaid') AS fee_status
            FROM students s
            JOIN batches b ON s.batch_id = b.id
            LEFT JOIN fees f ON f.student_id = s.id AND f.month = %s AND f.year = %s
            WHERE b.dojo_id = %s
            ORDER BY b.name, s.name
        """, (month, year, dojo_id))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/fees', methods=['POST'], strict_slashes=False)
def update_fee():
    data       = request.get_json()
    student_id = data.get('student_id')
    month      = data.get('month')
    year       = data.get('year')
    status     = data.get('status', 'unpaid')
    if not student_id or not month or not year:
        return jsonify({"error": "student_id, month, year are required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fees (student_id, month, year, status)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (student_id, month, year)
            DO UPDATE SET status = EXCLUDED.status
        """, (student_id, month, year, status))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# WHATSAPP NO-ABSENCE REPORT
# ==============================

@app.route('/api/whatsapp-report', strict_slashes=False)
def whatsapp_report():
    dojo_id  = request.args.get('dojo_id')
    month    = request.args.get('month')
    year     = request.args.get('year')
    batch_id = request.args.get('batch_id')

    if not dojo_id or not month or not year:
        return jsonify({"error": "dojo_id, month, year are required"}), 400

    month = int(month); year = int(year)
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if dojo_id == 'all':
            dojo_label = 'All Dojos'
        else:
            cur.execute("SELECT name FROM dojos WHERE id = %s", (dojo_id,))
            row = cur.fetchone()
            dojo_label = row['name'] if row else 'Dojo'

        if dojo_id == 'all':
            if batch_id:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name
                    FROM students s JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d ON b.dojo_id = d.id
                    WHERE s.batch_id = %s ORDER BY d.name, b.name, s.name
                """, (batch_id,))
            else:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name
                    FROM students s JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d ON b.dojo_id = d.id
                    ORDER BY d.name, b.name, s.name
                """)
        else:
            if batch_id:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name
                    FROM students s JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d ON b.dojo_id = d.id
                    WHERE b.dojo_id = %s AND s.batch_id = %s
                    ORDER BY b.name, s.name
                """, (dojo_id, batch_id))
            else:
                cur.execute("""
                    SELECT s.id, s.name, s.belt_level, b.name AS batch_name,
                           d.name AS dojo_name
                    FROM students s JOIN batches b ON s.batch_id = b.id
                    JOIN dojos d ON b.dojo_id = d.id
                    WHERE b.dojo_id = %s ORDER BY b.name, s.name
                """, (dojo_id,))

        all_students = cur.fetchall()
        student_ids  = [s['id'] for s in all_students]

        if student_ids:
            cur.execute("""
                SELECT DISTINCT student_id FROM attendance
                WHERE student_id = ANY(%s) AND status = 'absent'
                  AND EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s
            """, (student_ids, month, year))
            had_absence_ids = {r['student_id'] for r in cur.fetchall()}

            cur.execute("""
                SELECT DISTINCT student_id FROM attendance
                WHERE student_id = ANY(%s)
                  AND EXTRACT(MONTH FROM date) = %s AND EXTRACT(YEAR FROM date) = %s
            """, (student_ids, month, year))
            has_records_ids = {r['student_id'] for r in cur.fetchall()}
        else:
            had_absence_ids = set(); has_records_ids = set()

        stars = [s for s in all_students
                 if s['id'] not in had_absence_ids and s['id'] in has_records_ids]

        by_batch = defaultdict(list)
        for s in stars:
            by_batch[s['batch_name']].append(s)

        month_label = MONTH_NAMES[month]
        lines = [
            f"🥋 *ZERO ABSENCES — {month_label.upper()} {year}*",
            f"🏯 {dojo_label}",
            "━━━━━━━━━━━━━━━━━",
            f"⭐ Students with *zero absences* this month:\n"
        ]

        if not stars:
            lines.append("_(No students with zero absences this month)_")
        else:
            for batch_name, students in by_batch.items():
                lines.append(f"📌 *{batch_name}*")
                for i, s in enumerate(students, 1):
                    lines.append(f"  {i}. {s['name']} — {s['belt_level']}")
                lines.append("")
            lines.append(f"✅ {len(stars)} / {len(all_students)} students — Zero Absences!")

        lines.append("\nKeep training hard! 💪🥋 OSU!")
        return jsonify({"message": "\n".join(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# BELT TEST — GET STUDENTS FOR TEST
# With attendance stats since last belt test date
# ==============================

@app.route('/api/belt-test/students', strict_slashes=False)
def belt_test_students():
    dojo_id  = request.args.get('dojo_id')
    batch_id = request.args.get('batch_id')
    if not dojo_id:
        return jsonify({"error": "dojo_id is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if batch_id:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, b.name AS batch_name, b.id AS batch_id,
                       d.name AS dojo_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                JOIN dojos d ON b.dojo_id = d.id
                WHERE b.dojo_id = %s AND s.batch_id = %s
                ORDER BY b.name, s.name
            """, (dojo_id, batch_id))
        else:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, b.name AS batch_name, b.id AS batch_id,
                       d.name AS dojo_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                JOIN dojos d ON b.dojo_id = d.id
                WHERE b.dojo_id = %s
                ORDER BY b.name, s.name
            """, (dojo_id,))

        students = cur.fetchall()
        if not students:
            return jsonify([])

        student_ids = [s['id'] for s in students]

        # Try to find the last belt test date for this dojo
        # We'll use the most recent belt promotion recorded or fallback to 30 days ago
        # Since we don't have a belt_test_log table, we use the earliest attendance date
        # as a proxy — or just compute all-time stats
        cur.execute("""
            SELECT student_id,
                   SUM(CASE WHEN status='absent'  THEN 1 ELSE 0 END) AS absences,
                   SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present,
                   COUNT(*) AS total,
                   MIN(date) AS first_date,
                   MAX(date) AS last_date
            FROM attendance
            WHERE student_id = ANY(%s)
            GROUP BY student_id
        """, (student_ids,))
        att_map = {r['student_id']: r for r in cur.fetchall()}

        result = []
        for s in students:
            sid  = s['id']
            att  = att_map.get(sid)
            total   = int(att['total'])   if att else 0
            present = int(att['present']) if att else 0
            absences= int(att['absences'])if att else 0
            pct     = round(present / total * 100, 1) if total else 0
            result.append({
                **dict(s),
                "attendance_stats": {
                    "total": total,
                    "present": present,
                    "absences": absences,
                    "percentage": pct
                }
            })

        # Sort by absences ascending (fewest absences first = most dedicated)
        result.sort(key=lambda x: (x['attendance_stats']['absences'], -x['attendance_stats']['percentage']))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# BELT TEST — PROMOTE
# ==============================

@app.route('/api/belt-test/promote', methods=['POST'], strict_slashes=False)
def belt_test_promote():
    data           = request.get_json()
    ineligible_ids = set(data.get('ineligible_ids', []))
    student_ids    = data.get('student_ids', [])
    if not student_ids:
        return jsonify({"error": "student_ids is required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, belt_level FROM students WHERE id = ANY(%s)", (student_ids,))
        rows = cur.fetchall()

        promoted = []
        skipped  = []

        cur2 = conn.cursor()
        for row in rows:
            sid   = row['id']
            belt  = row['belt_level']
            if sid in ineligible_ids:
                skipped.append({"id": sid, "belt": belt})
                continue
            new_belt = next_belt(belt)
            cur2.execute("UPDATE students SET belt_level=%s WHERE id=%s", (new_belt, sid))
            promoted.append({"id": sid, "old_belt": belt, "new_belt": new_belt})

        conn.commit()
        cur2.close()
        return jsonify({"success": True, "promoted": promoted, "skipped": skipped})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ==============================
# HOME / TEST
# ==============================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/test')
def test():
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM dojos")
        data = cur.fetchall()
        cur.close(); conn.close()
        return str(data)
    except Exception as e:
        return str(e)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
