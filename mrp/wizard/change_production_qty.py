# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.tools.translate import _
import openerp.addons.decimal_precision as dp
from odoo.exceptions import UserError

class change_production_qty(models.TransientModel):
    _name = 'change.production.qty'
    _description = 'Change Quantity of Products'


    product_qty = fields.Float('Product Qty', digits=dp.get_precision('Product Unit of Measure'), required=True)


    def default_get(self, fields):
        """ To get default values for the object.
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param fields: List of fields for which we want default values
        @param context: A standard dictionary
        @return: A dictionary which of fields with values.
        """
        if context is None:
            context = {}
        res = super(change_production_qty, self).default_get(fields)
        prod_obj = self.env['mrp.production']
        prod = prod_obj.browse(context.get('active_id'))
        if 'product_qty' in fields:
            res.update({'product_qty': prod.product_qty})
        return res

    def _update_product_to_produce(self, prod, qty):
        move_lines_obj = self.env['stock.move']
        for m in prod.move_created_ids:
            move_lines_obj.write([m.id], {'product_uom_qty': qty})

    def change_prod_qty(self):
        """
        Changes the Quantity of Product.
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        @return:
        """
        record_id = context and context.get('active_id',False)
        assert record_id, _('Active Id not found')
        prod_obj = self.env['mrp.production']
        bom_obj = self.env['mrp.bom']
        move_obj = self.env['stock.move']
        uom_obj = self.env['product.uom']
        for wiz_qty in self.browse(ids):
            prod = prod_obj.browse(record_id)
            prod_obj.write([prod.id], {'product_qty': wiz_qty.product_qty})
            prod_obj.action_compute([prod.id])

            for move in prod.move_lines:
                bom_point = prod.bom_id
                bom_id = prod.bom_id.id
                if not bom_point:
                    bom_id = bom_obj._bom_find(product_id=prod.product_id.id)
                    if not bom_id:
                        raise UserError(_("Cannot find bill of material for this product."))
                    prod_obj.write([prod.id], {'bom_id': bom_id})
                    bom_point = bom_obj.browse([bom_id])[0]

                if not bom_id:
                    raise UserError(_("Cannot find bill of material for this product."))

                factor = uom_obj._compute_qty(prod.product_uom.id, prod.product_qty, bom_point.product_uom.id)
                product_details, workcenter_details = \
                    bom_obj._bom_explode(bom_point, prod.product_id, factor / bom_point.product_qty, [])
                for r in product_details:
                    if r['product_id'] == move.product_id.id:
                        move_obj.write([move.id], {'product_uom_qty': r['product_qty']})
            if prod.move_prod_id:
                move_obj.write([prod.move_prod_id.id], {'product_uom_qty' :  wiz_qty.product_qty})
            self._update_product_to_produce(prod, wiz_qty.product_qty)
        return {}
