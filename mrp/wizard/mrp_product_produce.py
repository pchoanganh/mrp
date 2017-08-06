# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, _
from odoo import fields, models
import openerp.addons.decimal_precision as dp


class mrp_product_produce_line(models.TransientModel):
    _name="mrp.product.produce.line"
    _description = "Product Produce Consume lines"


    product_id = fields.Many2one('product.product', string='Product')
    product_qty = fields.Float('Quantity (in default UoM)', digits=dp.get_precision('Product Unit of Measure'))
    lot_id = fields.Many2one('stock.production.lot', string='Lot')
    produce_id = fields.Many2one('mrp.product.produce', string="Produce")


class mrp_product_produce(models.TransientModel):
    _name = "mrp.product.produce"
    _description = "Product Produce"


    product_id = fields.Many2one('product.product', type='many2one')
    product_qty = fields.Float('Select Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    mode = fields.Selection([('consume_produce', 'Consume & Produce')
                                  ('consume', 'Consume Only')], 'Mode', required=True,
                                  help="'Consume only' mode will only consume the products with the quantity selected.\n"
                                        "'Consume & Produce' mode will consume as well as produce the products with the quantity selected "
                                        "and it will finish the production order when total ordered quantities are produced."),
        'lot_id': fields.Many2one('stock.production.lot', 'Lot'), #Should only be visible when it is consume and produce mode
    consume_lines = fields.One2many('mrp.product.produce.line', 'produce_id', 'Products Consumed')
    tracking = fields.Related('product_id', 'tracking', type='selection'
                                   selection=[('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')]),


    def on_change_qty(self, product_qty, consume_lines):
        """ 
            When changing the quantity of products to be produced it will 
            recalculate the number of raw materials needed according
            to the scheduled products and the already consumed/produced products
            It will return the consume lines needed for the products to be produced
            which the user can still adapt
        """
        prod_obj = self.env["mrp.production"]
        uom_obj = self.env["product.uom"]
        production = prod_obj.browse(context['active_id'])
        consume_lines = []
        new_consume_lines = []
        if product_qty > 0.0:
            product_uom_qty = uom_obj._compute_qty(production.product_uom.id, product_qty, production.product_id.uom_id.id)
            consume_lines = prod_obj._calculate_qty(production, product_qty=product_uom_qty)
        
        for consume in consume_lines:
            new_consume_lines.append([0, False, consume])
        return {'value': {'consume_lines': new_consume_lines}}


    def _get_product_qty(self):
        """ To obtain product quantity
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param context: A standard dictionary
        @return: Quantity
        """
        if context is None:
            context = {}
        prod = self.env['mrp.production'].browse(cr, uid,
                                context['active_id'])
        done = 0.0
        for move in prod.move_created_ids2:
            if move.product_id == prod.product_id:
                if not move.scrapped:
                    done += move.product_uom_qty # As uom of produced products and production order should correspond
        return prod.product_qty - done

    def _get_product_id(self):
        """ To obtain product id
        @return: id
        """
        prod=False
        if context and context.get("active_id"):
            prod = self.env['mrp.production'].browse(cr, uid,
                                    context['active_id'])
        return prod and prod.product_id.id or False
    
    def _get_track(self):
        prod = self._get_product_id(context=context)
        prod_obj = self.env["product.product"]
        return prod and prod_obj.browse(prod).tracking or 'none'

    _defaults = {
         'product_qty': _get_product_qty,
         'mode': lambda *x: 'consume_produce',
         'product_id': _get_product_id,
         'tracking': _get_track,
    }

    def do_produce(self):
        production_id = context.get('active_id', False)
        assert production_id, "Production Id should be specified in context as a Active ID."
        data = self.browse(ids[0])
        self.env['mrp.production'].action_produce(production_id,
                            data.product_qty, data.mode, data)
        return {}

    @api.onchange('consume_lines')
    def _onchange_consume_lines(self):
        '''
        The purpose of the method is to warn the user if we plan to consume more than one unit of
        a product with unique serial number.
        '''
        for product in self.consume_lines.mapped('product_id'):
            if product.tracking != 'serial':
                continue

            qty_by_lot = {}
            lines = self.consume_lines.filtered(lambda r: r.product_id == product)
            for line in lines:
                qty_by_lot.setdefault(line.lot_id, 0.0)
                qty_by_lot[line.lot_id] += line.product_qty

                if qty_by_lot[line.lot_id] > 1.0:
                    warning_mess = {
                        'title': _('Issue with lot quantity!'),
                        'message' : _('You plan to consume more than 1.00 unit of product %s with unique lot number %s') % \
                            (product.name, line.lot_id.name)
                    }
                    return {'warning': warning_mess}
