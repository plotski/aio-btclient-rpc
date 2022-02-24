extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
]

autosummary_generate = True
autosummary_imported_members = True

html_show_sourcelink = False  # Don't show links to rST code

templates_path = ['_templates']

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}
