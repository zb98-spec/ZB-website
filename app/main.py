from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

# Hub projects. Add an entry here each time a new project blueprint is built.
PROJECTS = [
    {
        "name": "Wine Library",
        "description": "Track every bottle in your cellar.",
        "endpoint": "wines.list_wines",
    },
]


@main_bp.route("/")
def index():
    return render_template("index.html", projects=PROJECTS)
