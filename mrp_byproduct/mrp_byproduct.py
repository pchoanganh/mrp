# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo import models
import openerp.addons.decimal_precision as dp
from odoo.tools.translate import _

class mrp_subproduct(models.Model):
    _name = 'mrp.subproduct'
    _description = 'Byproduct'
    _columns={
    product_id = fields.Many2one('product.product', 'Product', required=True)
    product_qty = fields.Float('Product Qty', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom = fields.Many2one('product.uom', 'Product Unit of Measure', required=True)
        'subproduct_type': fields.Selection([('fixed','Fixed'),('variable','Variable')], 'Quantity Type', required=True, help="Define how the quantity of byproducts will be set on the production orders using this BoM.\
  'Fixed' depicts a situation where the quantity of created byproduct is always equal to the quantity set on the BoM, regardless of how many are created in the production order.\
  By opposition, 'Variable' means that the quantity will be computed as\
    '(quantity of byproduct set on the BoM / quantity of manufactured product set on the BoM * quantity of manufactured product in the production order.)'"),
    bom_id = fields.Many2one('mrp.bom', 'BoM', ondelete='cascade')
    }
    _defaults={
        'subproduct_type': 'variable',
        'product_qty': lambda *a: 1.0,
    }

    def onchange_product_id(self, product_id):
        """ Changes UoM if product_id changes.
        @param product_id: Changed product_id
        @return: Dictionary of changed values
        """
        if product_id:
            prod = self.env['product.product'].browse(product_id)
            v = {'product_uom': prod.uom_id.id}
            return {'value': v}
        return {}

    def onchange_uom(self, product_id, product_uom):
        res = {'value':{}}
        if not product_uom or not product_id:
            return res
        product = self.env['product.product'].browse(product_id)
        uom = self.env['product.uom'].browse(product_uom)
        if uom.category_id.id != product.uom_id.category_id.id:
            res['warning'] = {'title': _('Warning'), 'message': _('The Product Unit of Measure you chose has a different category than in the product form.')}
            res['value'].update({'product_uom': product.uom_id.id})
        return res


class mrp_bom(models.Model):
    _name = 'mrp.bom'
    _description = 'Bill of Material'
    _inherit='mrp.bom'

    _columns={
    sub_products = fields.One2many('mrp.subproduct', 'bom_id', 'Byproducts', copy=True)
    }


class mrp_production(models.Model):
    _description = 'Production'
    _inherit= 'mrp.production'


    def action_confirm(self):
        """ Confirms production order and calculates quantity based on subproduct_type.
        @return: Newly generated picking Id.
        """
        move_obj = self.env['stock.move']
        picking_id = super(mrp_production,self).action_confirm(ids)
        product_uom_obj = self.env['product.uom']
        for production in self.browse(ids):
            source = production.product_id.property_stock_production.id
            if not production.bom_id:
                continue
            for sub_product in production.bom_id.sub_products:
                product_uom_factor = product_uom_obj._compute_qty(production.product_uom.id, production.product_qty, production.bom_id.product_uom.id)
                qty1 = sub_product.product_qty
                if sub_product.subproduct_type == 'variable':
                    if production.product_qty:
                        qty1 *= product_uom_factor / (production.bom_id.product_qty or 1.0)
                data = {
                    'name': 'PROD:'+production.name,
                    'date': production.date_planned,
                    'product_id': sub_product.product_id.id,
                    'product_uom_qty': qty1,
                    'product_uom': sub_product.product_uom.id,
                    'location_id': source,
                    'location_dest_id': production.location_dest_id.id,
                    'production_id': production.id
                }
                move_id = move_obj.create(data)
                move_obj.action_confirm([move_id])

        return picking_id

    def _get_subproduct_factor(self, production_id, move_id=None):
        """Compute the factor to compute the qty of procucts to produce for the given production_id. By default, 
            it's always equal to the quantity encoded in the production order or the production wizard, but with 
            the module mrp_byproduct installed it can differ for byproducts having type 'variable'.
        :param production_id: ID of the mrp.order
        :param move_id: ID of the stock move that needs to be produced. Identify the product to produce.
        :return: The factor to apply to the quantity that we should produce for the given production order and stock move.
        """
        sub_obj = self.env['mrp.subproduct']
        move_obj = self.env['stock.move']
        production_obj = self.env['mrp.production']
        production_browse = production_obj.browse(production_id)
        move_browse = move_obj.browse(move_id)
        subproduct_factor = 1
        sub_id = sub_obj.search(cr, uid,[('product_id', '=', move_browse.product_id.id),('bom_id', '=', production_browse.bom_id.id), ('subproduct_type', '=', 'variable')])
        if sub_id:
            subproduct_record = sub_obj.browse(cr ,uid, sub_id[0])
            if subproduct_record.bom_id.product_qty:
                subproduct_factor = subproduct_record.product_qty / subproduct_record.bom_id.product_qty
                return subproduct_factor
        return super(mrp_production, self)._get_subproduct_factor(production_id, move_id)


class change_production_qty(models.TransientModel):
    _inherit = 'change.production.qty'

    def _update_product_to_produce(self, prod, qty):
        bom_obj = self.env['mrp.bom']
        move_lines_obj = self.env['stock.move']
        prod_obj = self.env['mrp.production']
        for m in prod.move_created_ids:
            if m.product_id.id == prod.product_id.id:
                move_lines_obj.write([m.id], {'product_uom_qty': qty})
            else:
                for sub_product_line in prod.bom_id.sub_products:
                    if sub_product_line.product_id.id == m.product_id.id:
                        factor = prod_obj._get_subproduct_factor(prod.id, m.id)
                        subproduct_qty = sub_product_line.subproduct_type == 'variable' and qty * factor or sub_product_line.product_qty
                        move_lines_obj.write([m.id], {'product_uom_qty': subproduct_qty})
