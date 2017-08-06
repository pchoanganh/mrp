# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.tools import float_compare
from odoo.tools.translate import _
import openerp.addons.decimal_precision as dp

class stock_move_consume(models.TransientModel):
    _name = "stock.move.consume"
    _description = "Consume Products"


    product_id = fields.Many2one('product.product', 'Product', required=True, index=True)
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom = fields.Many2one('product.uom', 'Product Unit of Measure', required=True)
    location_id = fields.Many2one('stock.location', 'Location', required=True)
    restrict_lot_id = fields.Many2one('stock.production.lot', 'Lot')


    #TOFIX: product_uom should not have different category of default UOM of product. Qty should be convert into UOM of original move line before going in consume and scrap
    def default_get(self, fields):
        if context is None:
            context = {}
        res = super(stock_move_consume, self).default_get(fields)
        move = self.env['stock.move'].browse(context['active_id'])
        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_uom_qty})
        if 'location_id' in fields:
            res.update({'location_id': move.location_id.id})
        return res



    def do_move_consume(self):
        if context is None:
            context = {}
        move_obj = self.env['stock.move']
        uom_obj = self.env['product.uom']
        production_obj = self.env['mrp.production']
        move_ids = context['active_ids']
        move = move_obj.browse(move_ids[0])
        production_id = move.raw_material_production_id.id
        production = production_obj.browse(production_id)
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for data in self.browse(ids):
            qty = uom_obj._compute_qty(data['product_uom'].id, data.product_qty, data.product_id.uom_id.id)
            remaining_qty = move.product_qty - qty
            #check for product quantity is less than previously planned
            if float_compare(remaining_qty, 0, precision_digits=precision) >= 0:
                move_obj.action_consume(move_ids, qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id)
            else:
                consumed_qty = min(move.product_qty, qty)
                new_moves = move_obj.action_consume(move_ids, consumed_qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id)
                #consumed more in wizard than previously planned
                extra_more_qty = qty - consumed_qty
                #create new line for a remaining qty of the product
                extra_move_id = production_obj._make_consume_line_from_data(production, data.product_id, data.product_id.uom_id.id, extra_more_qty)
                move_obj.write([extra_move_id], {'restrict_lot_id': data.restrict_lot_id.id})
                move_obj.action_done([extra_move_id])
        return {'type': 'ir.actions.act_window_close'}
