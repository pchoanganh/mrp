# Update
# http://odoo-development.readthedocs.io/en/latest/migration/new-api.html#updates
# Rename file manifests.

# rename all manifests
find . -type f -name __openerp__.py -exec rename 's/__openerp__.py/__manifest__.py/' '{}' \;