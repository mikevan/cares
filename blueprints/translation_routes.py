"""
Translation Blueprint
Public-facing route for the CARES translation feature overview page.
No login required.
"""

from flask import Blueprint, render_template
from services.translation_service import SUPPORTED_LANGUAGES

translation_bp = Blueprint('translation', __name__)


@translation_bp.route('/about-translation')
def about():
    """Public page explaining CARES automatic translation capability."""
    return render_template(
        'about_translation.html',
        supported_languages=SUPPORTED_LANGUAGES,
    )
