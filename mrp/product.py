# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class product_template(models.Model):
    _inherit = "product.template"
    def _bom_orders_count(self, field_name, arg):
        Bom = self.env('mrp.bom')
        res = {}
        for product_tmpl_id in ids:
            nb = Bom.search_count([('product_tmpl_id', '=', product_tmpl_id)])
            res[product_tmpl_id] = {
                'bom_count': nb,
            }
        return res

    def _bom_orders_count_mo(self, name, arg):
        res = {}
        for product_tmpl_id in self.browse(ids):
            res[product_tmpl_id.id] = sum([p.mo_count for p in product_tmpl_id.product_variant_ids])
        return res


    bom_ids = fields.One2many('mrp.bom', 'product_tmpl_id','Bill of Materials')
    bom_count = fields.Integer(compute="_bom_orders_count", string='# Bill of Material',)
    mo_count = fields.Integer(compute="_bom_orders_count_mo", string='# Manufacturing Orders', )
    produce_delay = fields.Float('Manufacturing Lead Time', help="Average delay in days to produce this product. In the case of multi-level BOM, the manufacturing lead times of the components will be added.")


    _defaults = {
        'produce_delay': 1,
    }
    
    
    def action_view_mos(self):
        products = self._get_products(ids)
        result = self._get_act_window_dict('mrp.act_product_mrp_production')
        if len(ids) == 1 and len(products) == 1:
            result['context'] = "{'default_product_id': " + str(products[0]) + ", 'search_default_product_id': " + str(products[0]) + "}"
        else:
            result['domain'] = "[('product_id','in',[" + ','.join(map(str, products)) + "])]"
            result['context'] = "{}"
        return result


class product_product(models.Model):
    _inherit = "product.product"
    def _bom_orders_count(self, field_name, arg):
        Production = self.env('mrp.production')
        res = {}
        for product_id in ids:
            res[product_id] = Production.search_count(cr,uid, [('product_id', '=', product_id)])
        return res


    mo_count = fields.Integer(compute="_bom_orders_count", string='# Manufacturing Orders', )


    def action_view_bom(self):
        result = self.env["product.template"]._get_act_window_dict('mrp.product_open_bom')
        templates = [product.product_tmpl_id.id for product in self.browse(ids)]
        # bom specific to this variant or global to template
        context = {
            'search_default_product_tmpl_id': templates[0],
            'search_default_product_id': ids[0],
            'default_product_tmpl_id': templates[0],
            'default_product_id': ids[0],
        }
        result['context'] = str(context)
        return result
