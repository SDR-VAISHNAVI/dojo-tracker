from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import date
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

# ==============================
# SUPABASE CONNECTION
# ==============================

DATABASE_URL = "postgresql://postgres.losiamfhydgdsojghcui:VaishnaviGiri@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

def get_conn():
    return psycopg2.connect(DATABASE_URL)


# ==============================
# DOJOS
# ==============================

@app.route('/api/dojos', strict_slashes=False)
def get_dojos():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, name
            FROM dojos
            ORDER BY name
        """)
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


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
            SELECT id, name
            FROM batches
            WHERE dojo_id = %s
            ORDER BY name
        """, (dojo_id,))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# STUDENTS
# ==============================

@app.route('/api/students', strict_slashes=False)
def get_students():
    batch_id = request.args.get('batch_id')
    dojo_id = request.args.get('dojo_id')

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if batch_id:
            cur.execute("""
                SELECT s.id,
                       s.name,
                       s.belt_level,
                       s.batch_id,
                       b.dojo_id,
                       b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE s.batch_id = %s
                ORDER BY s.name
            """, (batch_id,))

        elif dojo_id:
            cur.execute("""
                SELECT s.id,
                       s.name,
                       s.belt_level,
                       s.batch_id,
                       b.dojo_id,
                       b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE b.dojo_id = %s
                ORDER BY s.name
            """, (dojo_id,))

        else:
            return jsonify({"error": "batch_id or dojo_id is required"}), 400

        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# STUDENT STATS
# ==============================

@app.route('/api/students/stats', strict_slashes=False)
def student_stats():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT COUNT(*) AS total FROM students")
        total = cur.fetchone()['total']

        cur.execute("""
            SELECT COUNT(*) AS black
            FROM students
            WHERE LOWER(belt_level) LIKE '%black%'
        """)
        black = cur.fetchone()['black']

        cur.execute("SELECT COUNT(*) AS batches FROM batches")
        batches = cur.fetchone()['batches']

        return jsonify({"total": total, "black": black, "batches": batches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# ADD STUDENT
# ==============================

@app.route('/api/students', methods=['POST'], strict_slashes=False)
def add_student():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = (data.get('name') or '').strip()
    batch_id = data.get('batch_id')
    belt = (data.get('belt_level') or 'White Belt').strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not batch_id:
        return jsonify({"error": "batch_id is required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO students (name, batch_id, belt_level)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (name, batch_id, belt))
        student_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"success": True, "id": student_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# UPDATE STUDENT
# ==============================

@app.route('/api/students/<int:student_id>', methods=['PUT'], strict_slashes=False)
def update_student(student_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = (data.get('name') or '').strip()
    batch_id = data.get('batch_id')
    belt = (data.get('belt_level') or 'White Belt').strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not batch_id:
        return jsonify({"error": "batch_id is required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE students
            SET name=%s, batch_id=%s, belt_level=%s
            WHERE id=%s
        """, (name, batch_id, belt, student_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# DELETE STUDENT
# ==============================

@app.route('/api/students/<int:student_id>', methods=['DELETE'], strict_slashes=False)
def delete_student(student_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM attendance WHERE student_id=%s", (student_id,))
        cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


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
                INSERT INTO attendance (student_id, status, date, class_number)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (student_id, date, class_number)
                DO UPDATE SET status = EXCLUDED.status
            """, (r['student_id'], r['status'], att_date))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# NO-ABSENCES MONTHLY REPORT
# Returns students who were NEVER marked absent in a given month.
# Unmarked days are ignored — only explicit 'absent' records disqualify.
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

        # Fetch all students in the dojo (optionally filtered by batch)
        if batch_id:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, b.name AS batch_name, b.id AS batch_id
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE b.dojo_id = %s AND s.batch_id = %s
                ORDER BY b.name, s.name
            """, (dojo_id, batch_id))
        else:
            cur.execute("""
                SELECT s.id, s.name, s.belt_level, b.name AS batch_name, b.id AS batch_id
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE b.dojo_id = %s
                ORDER BY b.name, s.name
            """, (dojo_id,))

        all_students = cur.fetchall()

        if not all_students:
            return jsonify({
                "no_absence_students": [],
                "had_absence_students": [],
                "total_students": 0
            })

        student_ids = [s['id'] for s in all_students]

        # Get students who had AT LEAST ONE 'absent' record this month
        cur.execute("""
            SELECT DISTINCT student_id
            FROM attendance
            WHERE student_id = ANY(%s)
              AND status = 'absent'
              AND EXTRACT(MONTH FROM date) = %s
              AND EXTRACT(YEAR  FROM date) = %s
        """, (student_ids, int(month), int(year)))

        had_absence_ids = {row['student_id'] for row in cur.fetchall()}

        # Get students who had AT LEAST ONE attendance record this month (any status)
        cur.execute("""
            SELECT DISTINCT student_id
            FROM attendance
            WHERE student_id = ANY(%s)
              AND EXTRACT(MONTH FROM date) = %s
              AND EXTRACT(YEAR  FROM date) = %s
        """, (student_ids, int(month), int(year)))

        has_any_record_ids = {row['student_id'] for row in cur.fetchall()}

        no_absence_students = []
        had_absence_students = []

        for s in all_students:
            sid = s['id']
            if sid in had_absence_ids:
                had_absence_students.append(dict(s))
            elif sid in has_any_record_ids:
                # Has records but none are 'absent' → qualifies
                no_absence_students.append(dict(s))
            # Students with NO records at all are excluded from both lists

        return jsonify({
            "no_absence_students":  no_absence_students,
            "had_absence_students": had_absence_students,
            "total_students":       len(all_students)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# REPORTS
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
            FROM students s
            JOIN batches b ON s.batch_id = b.id
            WHERE s.batch_id = %s
            ORDER BY s.name
        """, (batch_id,))
        students_list = cur.fetchall()

        if not students_list:
            return jsonify([])

        cur.execute("""
            SELECT a.student_id, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.date = %s
              AND s.batch_id = %s
        """, (att_date, batch_id))
        attendance_rows = cur.fetchall()

        attendance_map = {r['student_id']: r['status'] for r in attendance_rows}

        result = []
        for s in students_list:
            result.append({
                "id":         s["id"],
                "name":       s["name"],
                "belt_level": s["belt_level"],
                "batch_name": s.get("batch_name", ""),
                "status":     attendance_map.get(s["id"])
            })

        total    = len(result)
        present  = sum(1 for r in result if r["status"] == "present")
        absent   = sum(1 for r in result if r["status"] == "absent")
        unmarked = sum(1 for r in result if r["status"] is None)
        percent  = round((present / total * 100), 1) if total else 0

        return jsonify({
            "students": result,
            "summary": {
                "total":    total,
                "present":  present,
                "absent":   absent,
                "unmarked": unmarked,
                "percent":  percent
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# HOME
# ==============================

@app.route('/')
def home():
    return render_template('index.html')


# ==============================
# TEST DATABASE
# ==============================

@app.route('/test')
def test():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM dojos")
        data = cur.fetchall()
        cur.close()
        conn.close()
        return str(data)
    except Exception as e:
        return str(e)


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
            LEFT JOIN fees f
                ON f.student_id = s.id
               AND f.month = %s
               AND f.year  = %s
            WHERE b.dojo_id = %s
            ORDER BY b.name, s.name
        """, (month, year, dojo_id))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


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
        # Use a schema that works with both the old (amount_due required) and
        # new (status-only) fees table. We attempt insert with amount_due=0
        # as fallback if the column exists.
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
        # Try with amount_due column for legacy schema
        try:
            cur2 = conn.cursor()
            cur2.execute("""
                INSERT INTO fees (student_id, month, year, amount_due, status)
                VALUES (%s, %s, %s, 0, %s)
                ON CONFLICT (student_id, month, year)
                DO UPDATE SET status = EXCLUDED.status
            """, (student_id, month, year, status))
            conn.commit()
            cur2.close()
            return jsonify({"success": True})
        except Exception as e2:
            conn.rollback()
            return jsonify({"error": str(e2)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# WHATSAPP MONTH REPORT
# ==============================

@app.route('/api/whatsapp-report', strict_slashes=False)
def whatsapp_report():
    from collections import defaultdict

    dojo_id = request.args.get('dojo_id')
    month   = request.args.get('month')
    year    = request.args.get('year')

    if not dojo_id or not month or not year:
        return jsonify({"error": "dojo_id, month, year are required"}), 400

    month = int(month)
    year  = int(year)

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT name FROM dojos WHERE id = %s", (dojo_id,))
        dojo = cur.fetchone()
        dojo_name = dojo['name'] if dojo else 'Dojo'

        cur.execute("""
            SELECT COUNT(DISTINCT a.date) AS class_days
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN batches  b ON s.batch_id   = b.id
            WHERE b.dojo_id = %s
              AND EXTRACT(MONTH FROM a.date) = %s
              AND EXTRACT(YEAR  FROM a.date) = %s
        """, (dojo_id, month, year))
        class_days = cur.fetchone()['class_days'] or 0

        cur.execute("""
            SELECT s.id, s.name, b.name AS batch_name,
                   COUNT(a.id) FILTER (WHERE a.status = 'present') AS present_count
            FROM students s
            JOIN batches b ON s.batch_id = b.id
            LEFT JOIN attendance a
                ON a.student_id = s.id
               AND EXTRACT(MONTH FROM a.date) = %s
               AND EXTRACT(YEAR  FROM a.date) = %s
            WHERE b.dojo_id = %s
            GROUP BY s.id, s.name, b.name
            ORDER BY b.name, s.name
        """, (month, year, dojo_id))
        students = cur.fetchall()

        batches = defaultdict(list)
        for s in students:
            batches[s['batch_name']].append(s)

        month_names = ['','January','February','March','April','May','June',
                       'July','August','September','October','November','December']
        month_label = month_names[month]

        lines = []
        lines.append(f"🥋 *{dojo_name} — {month_label} {year} Report*")
        lines.append(f"📅 Total class days this month: *{class_days}*")
        lines.append("")

        for batch_name, batch_students in batches.items():
            stars = [s for s in batch_students
                     if class_days > 0 and s['present_count'] == class_days]
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"📌 *{batch_name}*")
            if stars:
                lines.append(f"⭐ *Perfect Attendance ({class_days}/{class_days} classes):*")
                for s in stars:
                    lines.append(f"   ✅ {s['name']}")
            else:
                lines.append("   _(No perfect attendance this month)_")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━")
        lines.append("_Keep training hard! OSU! 🥋_")

        return jsonify({"message": "\n".join(lines)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==============================
# RUN
# ==============================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
