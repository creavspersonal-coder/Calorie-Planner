# Calorie Planner Project
# Author: Aditya

import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, g, flash

DB_PATH = Path(__file__).parent / "meals.db"

app = Flask(__name__)
app.secret_key = "change-this-to-a-secure-random-string"

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "very": 1.725,
    "extreme": 1.9
}

CAL_PER_G_PROTEIN = 4
CAL_PER_G_CARB = 4
CAL_PER_G_FAT = 9
SAFETY_FLOOR_KCAL = 1200  

def compute_bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    sex = (sex or "").lower()
    if sex in ("male", "m"):
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    elif sex in ("female", "f"):
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr_m = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        bmr_f = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        bmr = (bmr_m + bmr_f) / 2
    return round(bmr, 1)

def maintenance_calories(bmr: float, activity: str) -> float:
    factor = ACTIVITY_MULTIPLIERS.get(activity, 1.2)
    return round(bmr * factor, 1)

def goal_calories(maintenance: float, goal: str) -> int:
    goal = (goal or "").lower()
    if goal == "lose":
        target = maintenance * 0.85
    elif goal == "gain":
        target = maintenance * 1.10
    else:
        target = maintenance
    return max(int(round(target)), SAFETY_FLOOR_KCAL)

def macro_targets(weight_kg: float, target_cal: int, protein_per_kg: float = 2.0, fat_pct: float = 0.25):
    protein_g = protein_per_kg * weight_kg
    protein_cals = protein_g * CAL_PER_G_PROTEIN
    fat_cals = fat_pct * target_cal
    fat_g = fat_cals / CAL_PER_G_FAT
    carbs_cals = target_cal - (protein_cals + fat_cals)
    carbs_g = max(0, carbs_cals / CAL_PER_G_CARB)
    return {
        "protein_g": round(protein_g, 1),
        "fat_g": round(fat_g, 1),
        "carbs_g": round(carbs_g, 1)
    }

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
    return db

def init_db_if_missing():
    if DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
    CREATE TABLE meals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        meal_type TEXT NOT NULL,
        calories INTEGER NOT NULL,
        protein_g REAL NOT NULL,
        carbs_g REAL NOT NULL,
        fat_g REAL NOT NULL,
        tags TEXT
    )
    """)
    seed_meals = [
        ("Oats with milk & banana", "breakfast", 350, 12, 60, 7, "vegetarian"),
        ("Paneer curry + brown rice", "lunch", 650, 30, 75, 20, "vegetarian"),
        ("Dal + rotis + veg", "dinner", 600, 25, 80, 15, "vegetarian"),
        ("Protein shake + banana", "snack", 250, 25, 30, 3, ""),
    ]
    c.executemany("INSERT INTO meals (name, meal_type, calories, protein_g, carbs_g, fat_g, tags) VALUES (?,?,?,?,?,?,?)", seed_meals)
    conn.commit()
    conn.close()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def pick_meal_for_slot(slot: str, slot_target_kcal: int):
    db = get_db()
    rows = db.execute("SELECT * FROM meals WHERE meal_type = ?", (slot,)).fetchall()
    best = min(rows, key=lambda r: abs(r["calories"] - slot_target_kcal))
    return dict(best)

def generate_day_plan(target_cal: int):
    slots = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30, "snack": 0.10}
    plan = {}
    for slot, pct in slots.items():
        slot_target = int(round(target_cal * pct))
        plan[slot] = pick_meal_for_slot(slot, slot_target)
    return plan

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    try:
        data = request.form
        name = data.get("name", "").strip()
        sex = data.get("sex", "")
        age = int(data.get("age", 0))
        weight = float(data.get("weight", 0))
        height = float(data.get("height", 0))
        activity = data.get("activity", "sedentary")
        goal = data.get("goal", "maintain")

        if age <= 0 or weight <= 0 or height <= 0:
            flash("Please enter valid numbers.")
            return redirect(url_for("index"))

        bmr = compute_bmr(sex, weight, height, age)
        maintenance = maintenance_calories(bmr, activity)
        target = goal_calories(maintenance, goal)
        macros = macro_targets(weight, target)

        plan = generate_day_plan(target)

        result = {
            "name": name or "User",
            "bmr": bmr,
            "maintenance": maintenance,
            "target": target,
            "macros": macros,
            "plan": plan,
        }
        return render_template("result.html", result=result)
    except Exception as e:
        flash(f"Error: {e}")
        return redirect(url_for("index"))

if __name__ == "__main__":
    init_db_if_missing()
    app.run(debug=True, port=5000)
