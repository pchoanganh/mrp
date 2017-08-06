# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class make_invoice(models.TransientModel):
    _name = 'mrp.repair.make_invoice'
    _description = 'Make Invoice'


       group = fields.Boolean('Group by partner invoice address')


    def make_invoices(self):
        """ Generates invoice(s) of selected records.
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        @return: Loads the view of new invoice(s).
        """
        if context is None:
            context = {}
        inv = self.browse(ids[0])
        order_obj = self.env['mrp.repair']
        mod_obj = self.env['ir.model.data']
        newinv = order_obj.action_invoice_create(context['active_ids'],
                                                 group=inv.group,context=context)

        # We have to trigger the workflow of the given repairs, otherwise they remain 'to be invoiced'.
        # Note that the signal 'action_invoice_create' will trigger another call to the method 'action_invoice_create',
        # but that second call will not do anything, since the repairs are already invoiced.
        order_obj.signal_workflow(context['active_ids'], 'action_invoice_create')

        form_res = mod_obj.get_object_reference('account', 'invoice_form')
        form_id = form_res and form_res[1] or False
        tree_res = mod_obj.get_object_reference('account', 'invoice_tree')
        tree_id = tree_res and tree_res[1] or False

        return {
            'domain': [('id','in', newinv.values())],
            'name': 'Invoices',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.invoice',
            'view_id': False,
            'views': [(tree_id, 'tree'),(form_id, 'form')],
            'context': "{'type':'out_invoice'}",
            'type': 'ir.actions.act_window'
        }
