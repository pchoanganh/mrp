# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time

from odoo import fields
from odoo import models
from odoo.tools.translate import _
from odoo import SUPERUSER_ID
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare
from odoo.exceptions import UserError

class StockMove(models.Model):
    _inherit = 'stock.move'


    production_id = fields.Many2one('mrp.production', 'Production Order for Produced Products', index=True, copy=False)
    raw_material_production_id = fields.Many2one('mrp.production', 'Production Order for Raw Materials', index=True)
    consumed_for = fields.Many2one('stock.move', 'Consumed for', help='Technical field used to make the traceability of produced products')


    def check_tracking(self, move, ops):
        super(StockMove, self).check_tracking(move, ops)
        if move.raw_material_production_id and move.product_id.tracking!='none' and move.location_dest_id.usage == 'production' and move.raw_material_production_id.product_id.tracking != 'none' and not move.consumed_for:
            raise UserError(_("Because the product %s requires it, you must assign a serial number to your raw material %s to proceed further in your production. Please use the 'Produce' button to do so.") % (move.raw_material_production_id.product_id.name, move.product_id.name))

    def _action_explode(self, move):
        """ Explodes pickings.
        @param move: Stock moves
        @return: True
        """
        if context is None:
            context = {}
        bom_obj = self.env['mrp.bom']
        move_obj = self.env['stock.move']
        prod_obj = self.env["product.product"]
        proc_obj = self.env["procurement.order"]
        uom_obj = self.env["product.uom"]
        to_explode_again_ids = []
        property_ids = context.get('property_ids') or []
        bis = bom_obj._bom_find(product_id=move.product_id.id, properties=property_ids)
        bom_point = bom_obj.browse(bis)
        if bis and bom_point.type == 'phantom':
            processed_ids = []
            factor = uom_obj._compute_qty(move.product_uom.id, move.product_uom_qty, bom_point.product_uom.id) / bom_point.product_qty
            res = bom_obj._bom_explode(bom_point, move.product_id, factor, property_ids)

            for line in res[0]:
                product = prod_obj.browse(line['product_id'])
                if product.type in ['product', 'consu']:
                    valdef = {
                        'picking_id': move.picking_id.id if move.picking_id else False,
                        'product_id': line['product_id'],
                        'product_uom': line['product_uom'],
                        'product_uom_qty': line['product_qty'],
                        'state': 'draft',  #will be confirmed below
                        'name': line['name'],
                        'procurement_id': move.procurement_id.id,
                        'split_from': move.id, #Needed in order to keep sale connection, but will be removed by unlink
                        'price_unit': product.standard_price,
                    }
                    mid = move_obj.copy(move.id, default=valdef)
                    to_explode_again_ids.append(mid)
                else:
                    if product._need_procurement():
                        valdef = {
                            'name': move.rule_id and move.rule_id.name or "/",
                            'origin': move.origin,
                            'company_id': move.company_id and move.company_id.id or False,
                            'date_planned': move.date,
                            'product_id': line['product_id'],
                            'product_qty': line['product_qty'],
                            'product_uom': line['product_uom'],
                            'group_id': move.group_id.id,
                            'priority': move.priority,
                            'partner_dest_id': move.partner_id.id,
                            }
                        if move.procurement_id:
                            proc = proc_obj.copy(move.procurement_id.id, default=valdef)
                        else:
                            proc = proc_obj.create(valdef)
                        proc_obj.run([proc]) #could be omitted
            
            #check if new moves needs to be exploded
            if to_explode_again_ids:
                for new_move in self.browse(to_explode_again_ids):
                    processed_ids.extend(self._action_explode(new_move))
            
            if not move.split_from and move.procurement_id:
                # Check if procurements have been made to wait for
                moves = move.procurement_id.move_ids
                if len(moves) == 1:
                    proc_obj.write([move.procurement_id.id], {'state': 'done'})

            if processed_ids and move.state == 'assigned':
                # Set the state of resulting moves according to 'assigned' as the original move is assigned
                move_obj.write(list(set(processed_ids) - set([move.id])), {'state': 'assigned'})
                
            #delete the move with original product which is not relevant anymore
            move_obj.unlink([move.id])
            #return list of newly created move
            return processed_ids

        return [move.id]

    def action_confirm(self):
        move_ids = []
        for move in self.browse(ids):
            #in order to explode a move, we must have a picking_type_id on that move because otherwise the move
            #won't be assigned to a picking and it would be weird to explode a move into several if they aren't
            #all grouped in the same picking.
            if move.picking_type_id:
                move_ids.extend(self._action_explode(move))
            else:
                move_ids.append(move.id)

        #we go further with the list of ids potentially changed by action_explode
        return super(StockMove, self).action_confirm(move_ids)

    def action_consume(self, product_qty, location_id=False, restrict_lot_id=False, restrict_partner_id=False,
                       consumed_for=False):
        """ Consumed product with specific quantity from specific source location.
        @param product_qty: Consumed/produced product quantity (= in quantity of UoM of product)
        @param location_id: Source location
        @param restrict_lot_id: optionnal parameter that allows to restrict the choice of quants on this specific lot
        @param restrict_partner_id: optionnal parameter that allows to restrict the choice of quants to this specific partner
        @param consumed_for: optionnal parameter given to this function to make the link between raw material consumed and produced product, for a better traceability
        @return: New lines created if not everything was consumed for this line
        """
        if context is None:
            context = {}
        res = []
        production_obj = self.env['mrp.production']

        if product_qty <= 0:
            raise UserError(_('Please provide proper quantity.'))
        #because of the action_confirm that can create extra moves in case of phantom bom, we need to make 2 loops
        ids2 = []
        for move in self.browse(ids):
            if move.state == 'draft':
                ids2.extend(self.action_confirm([move.id]))
            else:
                ids2.append(move.id)

        prod_orders = set()
        for move in self.browse(ids2):
            prod_orders.add(move.raw_material_production_id.id or move.production_id.id)
            move_qty = move.product_qty
            if move_qty <= 0:
                raise UserError(_('Cannot consume a move with negative or zero quantity.'))
            quantity_rest = move_qty - product_qty
            # Compare with numbers of move uom as we want to avoid a split with 0 qty
            quantity_rest_uom = move.product_uom_qty - self.env["product.uom"]._compute_qty_obj(move.product_id.uom_id, product_qty, move.product_uom)
            if float_compare(quantity_rest_uom, 0, precision_rounding=move.product_uom.rounding) != 0:
                new_mov = self.split(move, quantity_rest)
                if move.production_id:
                    self.write([new_mov], {'production_id': move.production_id.id})
                res.append(new_mov)
            vals = {'restrict_lot_id': restrict_lot_id,
                    'restrict_partner_id': restrict_partner_id,
                    'consumed_for': consumed_for}
            if location_id:
                vals.update({'location_id': location_id})
            self.write([move.id], vals)
        # Original moves will be the quantities consumed, so they need to be done
        self.action_done(ids2)
        if res:
            self.action_assign(res)
        if prod_orders:
            production_obj.signal_workflow(list(prod_orders), 'button_produce')
        return res

    def action_scrap(self, product_qty, location_id, restrict_lot_id=False, restrict_partner_id=False):
        """ Move the scrap/damaged product into scrap location
        @param product_qty: Scraped product quantity
        @param location_id: Scrap location
        @return: Scraped lines
        """
        res = []
        production_obj = self.env['mrp.production']
        for move in self.browse(ids):
            new_moves = super(StockMove, self).action_scrap([move.id], product_qty, location_id,
                                                            restrict_lot_id=restrict_lot_id,
                                                            restrict_partner_id=restrict_partner_id)
            #If we are not scrapping our whole move, tracking and lot references must not be removed
            production_ids = production_obj.search([('move_lines', 'in', [move.id])])
            for prod_id in production_ids:
                production_obj.signal_workflow([prod_id], 'button_produce')
            if move.production_id.id:
                self.write(new_moves, {'production_id': move.production_id.id})
            res += new_moves
        return res

    def write(self, vals):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = super(StockMove, self).write(ids, vals)
        from odoo import workflow
        if vals.get('state') == 'assigned':
            moves = self.browse(ids)
            orders = list(set([x.raw_material_production_id.id for x in moves if x.raw_material_production_id and x.raw_material_production_id.state == 'confirmed']))
            for order_id in orders:
                if self.env['mrp.production'].test_ready([order_id]):
                    workflow.trg_validate(uid, 'mrp.production', order_id, 'moves_ready', cr)
        return res

class stock_warehouse(models.Model):
    _inherit = 'stock.warehouse'

        'manufacture_to_resupply': fields.Boolean('Manufacture in this Warehouse', 
                                                  help="When products are manufactured, they can be manufactured in this warehouse."),
    manufacture_pull_id = fields.Many2one('procurement.rule', 'Manufacture Rule')


    _defaults = {
        'manufacture_to_resupply': True,
    }

    def _get_manufacture_pull_rule(self, warehouse):
        route_obj = self.env['stock.location.route']
        data_obj = self.env['ir.model.data']
        try:
            manufacture_route_id = data_obj.get_object_reference('mrp', 'route_warehouse0_manufacture')[1]
        except:
            manufacture_route_id = route_obj.search([('name', 'like', _('Manufacture'))])
            manufacture_route_id = manufacture_route_id and manufacture_route_id[0] or False
        if not manufacture_route_id:
            raise UserError(_('Can\'t find any generic Manufacture route.'))

        return {
            'name': self._format_routename(warehouse, _(' Manufacture')),
            'location_id': warehouse.lot_stock_id.id,
            'route_id': manufacture_route_id,
            'action': 'manufacture',
            'picking_type_id': warehouse.int_type_id.id,
            'propagate': False, 
            'warehouse_id': warehouse.id,
        }

    def create_routes(self, warehouse):
        pull_obj = self.env['procurement.rule']
        res = super(stock_warehouse, self).create_routes(ids, warehouse)
        if warehouse.manufacture_to_resupply:
            manufacture_pull_vals = self._get_manufacture_pull_rule(warehouse)
            manufacture_pull_id = pull_obj.create(manufacture_pull_vals)
            res['manufacture_pull_id'] = manufacture_pull_id
        return res

    def write(self, vals):
        pull_obj = self.env['procurement.rule']
        if isinstance(ids, (int, long)):
            ids = [ids]

        if 'manufacture_to_resupply' in vals:
            if vals.get("manufacture_to_resupply"):
                for warehouse in self.browse(ids):
                    if not warehouse.manufacture_pull_id:
                        manufacture_pull_vals = self._get_manufacture_pull_rule(warehouse)
                        manufacture_pull_id = pull_obj.create(manufacture_pull_vals)
                        vals['manufacture_pull_id'] = manufacture_pull_id
            else:
                for warehouse in self.browse(ids):
                    if warehouse.manufacture_pull_id:
                        pull_obj.unlink(warehouse.manufacture_pull_id.id)
        return super(stock_warehouse, self).write(ids, vals)

    def get_all_routes_for_wh(self, warehouse):
        all_routes = super(stock_warehouse, self).get_all_routes_for_wh(warehouse)
        if warehouse.manufacture_to_resupply and warehouse.manufacture_pull_id and warehouse.manufacture_pull_id.route_id:
            all_routes += [warehouse.manufacture_pull_id.route_id.id]
        return all_routes

    def _handle_renaming(self, warehouse, name, code):
        res = super(stock_warehouse, self)._handle_renaming(warehouse, name, code)
        pull_obj = self.env['procurement.rule']
        #change the manufacture procurement rule name
        if warehouse.manufacture_pull_id:
            pull_obj.write(warehouse.manufacture_pull_id.id, {'name': warehouse.manufacture_pull_id.name.replace(warehouse.name, name, 1)})
        return res

    def _get_all_products_to_resupply(self, warehouse):
        res = super(stock_warehouse, self)._get_all_products_to_resupply(warehouse)
        if warehouse.manufacture_pull_id and warehouse.manufacture_pull_id.route_id:
            for product_id in res:
                for route in self.env['product.product'].browse(product_id).route_ids:
                    if route.id == warehouse.manufacture_pull_id.route_id.id:
                        res.remove(product_id)
                        break
        return res
