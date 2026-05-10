from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from datetime import date
import os
import psycopg2

app = Flask(__name__)
CORS(app)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ── Dojos ────────────────────────────────────────────────

@app.route('/api/dojos', strict_slashes=False)
def get_dojos():
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM dojos ORDER BY name")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ── Batches ──────────────────────────────────────────────

@app.route('/api/batches', strict_slashes=False)
def get_batches():
    dojo_id = request.args.get('dojo_id')
    if not dojo_id:
        return jsonify({"error": "dojo_id is required"}), 400
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM batches WHERE dojo_id=%s ORDER BY name", (dojo_id,))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ── Students ─────────────────────────────────────────────

@app.route('/api/students', strict_slashes=False)
def get_students():
    """
    Supports two query modes:
      ?batch_id=X          → students in that batch (used by Attendance tab)
      ?dojo_id=X           → all students in a dojo, with batch_name (used by Students tab)
    """
    batch_id = request.args.get('batch_id')
    dojo_id  = request.args.get('dojo_id')

    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)

        if batch_id:
            cur.execute(
                """
                SELECT s.id, s.name, s.belt_level, s.batch_id,
                       b.dojo_id, b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE s.batch_id = %s
                ORDER BY s.name
                """,
                (batch_id,)
            )
        elif dojo_id:
            cur.execute(
                """
                SELECT s.id, s.name, s.belt_level, s.batch_id,
                       b.dojo_id, b.name AS batch_name
                FROM students s
                JOIN batches b ON s.batch_id = b.id
                WHERE b.dojo_id = %s
                ORDER BY s.name
                """,
                (dojo_id,)
            )
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
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS total FROM students")
        total = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS black FROM students WHERE LOWER(belt_level) = 'black'")
        black = cur.fetchone()['black']

        cur.execute("SELECT COUNT(*) AS batches FROM batches")
        batches = cur.fetchone()['batches']

        return jsonify({"total": total, "black": black, "batches": batches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students', methods=['POST'], strict_slashes=False)
def add_student():
    data = request.get_json()
    name      = (data.get('name') or '').strip()
    batch_id  = data.get('batch_id')
    belt      = (data.get('belt_level') or 'White').strip()

    if not name:     return jsonify({"error": "name is required"}), 400
    if not batch_id: return jsonify({"error": "batch_id is required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO students (name, batch_id, belt_level) VALUES (%s, %s, %s)",
            (name, batch_id, belt)
        )
        conn.commit()
        return jsonify({"success": True, "id": cur.lastrowid}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/api/students/<int:student_id>', methods=['PUT'], strict_slashes=False)
def update_student(student_id):
    data = request.get_json()
    name     = (data.get('name') or '').strip()
    batch_id = data.get('batch_id')
    belt     = (data.get('belt_level') or 'White').strip()

    if not name:     return jsonify({"error": "name is required"}), 400
    if not batch_id: return jsonify({"error": "batch_id is required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE students SET name=%s, batch_id=%s, belt_level=%s WHERE id=%s",
            (name, batch_id, belt, student_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Student not found"}), 404
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
        # Remove attendance records first (FK constraint)
        cur.execute("DELETE FROM attendance WHERE student_id=%s", (student_id,))
        cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Student not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


# ── Attendance ───────────────────────────────────────────

@app.route('/api/attendance', methods=['POST'], strict_slashes=False)
def mark_attendance():
    body = request.get_json()
    if not body or 'records' not in body:
        return jsonify({"error": "Missing records"}), 400
    records = body['records']
    if not isinstance(records, list) or not records:
        return jsonify({"error": "records must be a non-empty list"}), 400

    valid_statuses = {'present', 'absent', 'late'}
    for r in records:
        if r.get('status') not in valid_statuses:
            return jsonify({"error": f"Invalid status: {r.get('status')}"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor()
        for r in records:
            att_date = r.get('date') or date.today().isoformat()
            cur.execute(
                """
                INSERT INTO attendance (student_id, status, date)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status)
                """,
                (r['student_id'], r['status'], att_date)
            )
        conn.commit()
        return jsonify({"success": True, "saved": len(records)})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route('/')
def home():
    return render_template('index.html')
@app.route('/api/reports', strict_slashes=False)
def get_report():
    dojo_id  = request.args.get('dojo_id')
    batch_id = request.args.get('batch_id')
    att_date = request.args.get('date')

    if not (dojo_id and batch_id and att_date):
        return jsonify({"error": "dojo_id, batch_id, date required"}), 400

    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)

        # Get all students in batch
        cur.execute("""
            SELECT id, name, belt_level
            FROM students
            WHERE batch_id=%s
        """, (batch_id,))
        students_list = cur.fetchall()

        # Get attendance for that date
        cur.execute("""
            SELECT student_id, status
            FROM attendance
            WHERE date=%s
        """, (att_date,))
        attendance_rows = cur.fetchall()

        # Map attendance
        att_map = {r["student_id"]: r["status"] for r in attendance_rows}

        result = []
        present = absent = unmarked = 0

        for s in students_list:
            status = att_map.get(s["id"])

            if status == "present":
                present += 1
            elif status == "absent":
                absent += 1
            else:
                unmarked += 1

            result.append({
                "id": s["id"],
                "name": s["name"],
                "belt_level": s["belt_level"],
                "status": status
            })

        total = len(students_list)
        percent = round((present / total) * 100, 2) if total else 0

        return jsonify({
            "students": result,
            "summary": {
                "total": total,
                "present": present,
                "absent": absent,
                "unmarked": unmarked,
                "percent": percent
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
