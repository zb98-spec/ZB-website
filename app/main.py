from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

# Hub projects. Add an entry here each time a new project blueprint is built.
PROJECTS = [
    {
        "name": "Wine Library",
        "description": "Track every bottle in your cellar.",
        "endpoint": "wines.list_wines",
    },
    {
        "name": "Recipe Tracker",
        "description": "Save recipes, scale servings, and jot down notes.",
        "endpoint": "recipes.list_recipes",
    },
    {
        "name": "Grocery List",
        "description": "One shared shopping list for everyone in the app.",
        "endpoint": "grocery.list_items",
    },
]


@main_bp.route("/")
def index():
    return render_template("index.html", projects=PROJECTS)
