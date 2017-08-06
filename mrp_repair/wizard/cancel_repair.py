# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models,fields
from odoo.tools.translate import _
from odoo.exceptions import UserError

class repair_cancel(models.TransientModel):
    _name = 'mrp.repair.cancel'
    _description = 'Cancel Repair'

    def cancel_repair(self):
        """ Cancels the repair
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        @return:
        """
        if context is None:
            context = {}
        record_id = context and context.get('active_id', False) or False
        assert record_id, _('Active ID not Found')
        repair_order_obj = self.env['mrp.repair']
        repair_line_obj = self.env['mrp.repair.line']
        repair_order = repair_order_obj.browse(record_id)

        if repair_order.invoiced or repair_order.invoice_method == 'none':
            repair_order_obj.action_cancel([record_id])
        else:
            raise UserError(_('Repair order is not invoiced.'))

        return {'type': 'ir.actions.act_window_close'}

    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """ Changes the view dynamically
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param context: A standard dictionary
        @return: New arch of view.
        """
        if context is None:
            context = {}
        res = super(repair_cancel, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar,submenu=False)
        record_id = context and context.get('active_id', False) or False
        active_model = context.get('active_model')

        if not record_id or (active_model and active_model != 'mrp.repair'):
            return res

        repair_order = self.env['mrp.repair'].browse(record_id)
        if not repair_order.invoiced:
            res['arch'] = """
                <form string="Cancel Repair" version="7.0">
                    <header>
                        <button name="cancel_repair" string="_Yes" type="object" class="btn-primary"/>
                        <button string="Cancel" class="btn-default" special="cancel"/>
                    </header>
                    <label string="Do you want to continue?"/>
                </form>
            """
        return res
