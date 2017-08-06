# Fixing references on migration
# https://github.com/it-projects-llc/odoo-development/blob/master/docs/migration/fix-refs.rst
# 9.0- → 10.0+

# menu_hr_configuration
find . -type f -name '*.xml' | xargs sed -i 's/menu_hr_configuration/menu_human_resources_configuration/g'
# base.group_hr
find . -type f -name '*.csv'  -o -name '*.py' -o -name '*.xml'  | xargs sed -i 's/base.group_hr/hr.group_hr/g'
# website.salesteam_website_sales
find . -type f -name '*.csv'  -o -name '*.py' -o -name '*.xml'  | xargs sed -i 's/website.salesteam_website_sales/sales_team.salesteam_website_sales/g'
# base.group_sale_salesman
find . -type f -name '*.csv'  -o -name '*.py' -o -name '*.xml'  | xargs sed -i 's/base.group_sale_salesman/sales_team.group_sale_salesman/g'
# product.prod_config_main
find . -type f -name '*.xml' | xargs sed -i 's/product.prod_config_main/sale.prod_config_main/g'