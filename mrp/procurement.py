# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields
from odoo.tools.translate import _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo import SUPERUSER_ID

class procurement_rule(models.Model):
    _inherit = 'procurement.rule'

    def _get_action(self):
        return [('manufacture', _('Manufacture'))] + super(procurement_rule, self)._get_action(context=context)


class procurement_order(models.Model):
    _inherit = 'procurement.order'

    bom_id = fields.Many2one('mrp.bom', 'BoM', ondelete='cascade', index=True)
    property_ids = fields.Many2many('mrp.property', 'procurement_property_rel', 'procurement_id','property_id', 'Properties')
    production_id = fields.Many2one('mrp.production', 'Manufacturing Order')


    def propagate_cancels(self):
        for procurement in self.browse(ids):
            if procurement.rule_id.action == 'manufacture' and procurement.production_id:
                self.env['mrp.production'].action_cancel([procurement.production_id.id])
        return super(procurement_order, self).propagate_cancels(ids)

    def _run(self, procurement):
        if procurement.rule_id and procurement.rule_id.action == 'manufacture':
            #make a manufacturing order for the procurement
            return self.make_mo([procurement.id])[procurement.id]
        return super(procurement_order, self)._run(procurement)

    def _check(self, procurement):
        if procurement.production_id and procurement.production_id.state == 'done':  # TOCHECK: no better method? 
            return True
        return super(procurement_order, self)._check(procurement)

    def check_bom_exists(self):
        """ Finds the bill of material for the product from procurement order.
        @return: True or False
        """
        for procurement in self.browse(ids):
            properties = [x.id for x in procurement.property_ids]
            bom_id = self.env['mrp.bom']._bom_find(product_id=procurement.product_id.id,
                                                        properties=properties)
            if not bom_id:
                return False
        return True

    def _get_date_planned(self, procurement):
        format_date_planned = datetime.strptime(procurement.date_planned,
                                                DEFAULT_SERVER_DATETIME_FORMAT)
        date_planned = format_date_planned - relativedelta(days=procurement.product_id.produce_delay or 0.0)
        date_planned = date_planned - relativedelta(days=procurement.company_id.manufacturing_lead)
        return date_planned

    def _prepare_mo_vals(self, procurement):
        res_id = procurement.move_dest_id and procurement.move_dest_id.id or False
        newdate = self._get_date_planned(procurement)
        bom_obj = self.env['mrp.bom']
        if procurement.bom_id:
            bom_id = procurement.bom_id.id
            routing_id = procurement.bom_id.routing_id.id
        else:
            properties = [x.id for x in procurement.property_ids]
            bom_id = bom_obj._bom_find(product_id=procurement.product_id.id,
                                       properties=properties, company_id=procurement.company_id.id))
            bom = bom_obj.browse(bom_id)
            routing_id = bom.routing_id.id
        return {
            'origin': procurement.origin,
            'product_id': procurement.product_id.id,
            'product_qty': procurement.product_qty,
            'product_uom': procurement.product_uom.id,
            'location_src_id': procurement.rule_id.location_src_id.id or procurement.location_id.id,
            'location_dest_id': procurement.location_id.id,
            'bom_id': bom_id,
            'routing_id': routing_id,
            'date_planned': newdate.strftime('%Y-%m-%d %H:%M:%S'),
            'move_prod_id': res_id,
            'company_id': procurement.company_id.id,
        }

    def make_mo(self):
        """ Make Manufacturing(production) order from procurement
        @return: New created Production Orders procurement wise
        """
        res = {}
        production_obj = self.env['mrp.production']
        procurement_obj = self.env['procurement.order']
        for procurement in procurement_obj.browse(ids):
            if self.check_bom_exists([procurement.id]):
                #create the MO as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
                vals = self._prepare_mo_vals(procurement)
                produce_id = production_obj.create(vals, force_company=procurement.company_id.id))
                res[procurement.id] = produce_id
                self.write([procurement.id], {'production_id': produce_id})
                self.production_order_create_note(procurement)
                production_obj.action_compute([produce_id], properties=[x.id for x in procurement.property_ids])
                production_obj.signal_workflow([produce_id], 'button_confirm')
            else:
                res[procurement.id] = False
                self.message_post([procurement.id], body=_("No BoM exists for this product!"))
        return res

    def production_order_create_note(self, procurement):
        body = _("Manufacturing Order <em>%s</em> created.") % (procurement.production_id.name,)
        self.message_post([procurement.id], body=body)
