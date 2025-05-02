from odoo import models, fields, api
import random
import logging

_logger = logging.getLogger(__name__)

class LeadSyncLog(models.Model):
    _name = 'lead.sync.log'
    _description = 'Lead Sync Log'

    external_id = fields.Char('External ID', required=True, index=True)
    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    create_date = fields.Datetime('Created On', readonly=True)

class LeadSync(models.Model):
    _name = 'portal_lead_sync.lead_sync'
    _description = 'Portal Lead Synchronization'
    
    def _find_matching_team_by_city(self, city):
        """
        Find a sales team that matches the given city.
        
        Args:
            city (str): The city from the lead data
            
        Returns:
            crm.team: The matching sales team or False if none found
        """
        if not city:
            return False
            
        # First try exact match with team name
        teams = self.env['crm.team'].search([
            ('name', 'ilike', city)
        ])
        if teams:
            return teams[0]
            
        # Next, try matching with preferred_cities field
        all_teams = self.env['crm.team'].search([
            ('preferred_cities', '!=', False)
        ])
        
        # Normalize the city for better matching
        city = city.lower().strip()
        
        for team in all_teams:
            preferred_cities = [c.strip().lower() for c in team.preferred_cities.split(',')]
            if any(city in preferred_city or preferred_city in city for preferred_city in preferred_cities):
                return team
        
        return False
    
    def _assign_team_to_lead(self, lead_data):
        """
        Assign a team to the lead based on city matching logic with fallback to random assignment.
        
        Args:
            lead_data (dict): The lead data containing city information
            
        Returns:
            int: The ID of the selected sales team
        """
        # Extract city from lead data
        city = lead_data.get('city', '') or lead_data.get('contact_address', '')
        
        # Try to find a matching team based on city
        matching_team = self._find_matching_team_by_city(city)
        if matching_team:
            _logger.info(f"Lead assigned to team {matching_team.name} based on city match: {city}")
            return matching_team.id
            
        # Fallback to random assignment if no match found
        teams = self.env['crm.team'].search([])
        if teams:
            random_team = random.choice(teams)
            _logger.info(f"No city match found for {city}. Lead randomly assigned to: {random_team.name}")
            return random_team.id
        
        return False  # No teams available
    
    def sync_leads_from_portal(self):
        """Sync leads from external portal to Odoo CRM"""
        # ...existing code...
        
        for portal_lead in portal_leads:
            # Prepare lead values
            lead_values = {
                'name': portal_lead.get('name', 'Unknown Lead'),
                'email_from': portal_lead.get('email', False),
                'phone': portal_lead.get('phone', False),
                'description': portal_lead.get('description', ''),
                'city': portal_lead.get('city', ''),
                # Now assign team based on location instead of randomly
                'team_id': self._assign_team_to_lead(portal_lead),
            }
            
            # Create the lead with proper team assignment
            self.env['crm.lead'].create(lead_values)
            
        # ...existing code...
