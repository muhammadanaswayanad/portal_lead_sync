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
        
        # Normalize the city for better matching
        normalized_city = city.lower().strip()
        
        # First try exact match with team name
        teams = self.env['crm.team'].search([])
        for team in teams:
            # Check if team name contains city or vice versa (case insensitive)
            if normalized_city in team.name.lower() or team.name.lower() in normalized_city:
                _logger.debug(f"Found team match by name: {team.name} for city: {city}")
                return team
        
        # Next, try matching with preferred_cities field
        all_teams = self.env['crm.team'].search([
            ('preferred_cities', '!=', False)
        ])
        
        for team in all_teams:
            if not team.preferred_cities:
                continue
                
            _logger.debug(f"Checking team {team.name} with preferred cities: {team.preferred_cities}")
            preferred_cities = [c.strip().lower() for c in team.preferred_cities.split(',') if c.strip()]
            
            for preferred_city in preferred_cities:
                if preferred_city in normalized_city or normalized_city in preferred_city:
                    _logger.debug(f"Found team match by preferred city: {team.name} ({preferred_city}) for city: {city}")
                    return team
        
        _logger.debug(f"No team match found for city: {city}")
        return False

    def _assign_team_to_lead(self, lead_data):
        """
        Assign a team to the lead based on city matching logic with fallback to random assignment.
        Store the normalized city in preferred_branch field.
        
        Args:
            lead_data (dict): The lead data containing city information
            
        Returns:
            tuple: (team_id, normalized_city) - The ID of the selected sales team and normalized city
        """
        # Extract city from lead data
        city = lead_data.get('city', '') or lead_data.get('contact_address', '')
        
        # Normalize city for consistent matching
        normalized_city = city.lower().strip() if city else ''
        
        if not normalized_city:
            _logger.info("No city information provided in lead data, using random assignment")
            teams = self.env['crm.team'].search([])
            if teams:
                random_team = random.choice(teams)
                return random_team.id, normalized_city
            return False, normalized_city
        
        # Try to find a matching team based on city
        matching_team = self._find_matching_team_by_city(city)
        if matching_team:
            _logger.info(f"Lead assigned to team {matching_team.name} based on city match: {city}")
            return matching_team.id, normalized_city
            
        # Fallback to random assignment if no match found
        teams = self.env['crm.team'].search([])
        if teams:
            random_team = random.choice(teams)
            _logger.info(f"No city match found for '{city}'. Lead randomly assigned to: {random_team.name}")
            return random_team.id, normalized_city
        
        return False, normalized_city  # No teams available

    def sync_leads_from_portal(self):
        """Sync leads from external portal to Odoo CRM"""
        # This is where you would fetch data from your external portal API
        # For this example, I'm assuming portal_leads is a variable that contains the data
        
        # Example of what portal_leads might look like:
        # portal_leads = self._fetch_leads_from_external_api()
        
        # Placeholder for testing - replace with actual API call:
        portal_leads = self._get_portal_leads_data()
        
        if not portal_leads:
            _logger.warning("No leads fetched from portal")
            return
            
        _logger.info(f"Processing {len(portal_leads)} leads from portal")
        
        for portal_lead in portal_leads:
            # Check if we've already imported this lead
            if self._is_lead_already_imported(portal_lead.get('external_id')):
                _logger.info(f"Lead {portal_lead.get('external_id')} already imported, skipping")
                continue
                
            # Assign team and get normalized city
            team_id, normalized_city = self._assign_team_to_lead(portal_lead)
            
            # Prepare lead values
            lead_values = {
                'name': portal_lead.get('name', 'Unknown Lead'),
                'email_from': portal_lead.get('email', False),
                'phone': portal_lead.get('phone', False),
                'description': portal_lead.get('description', ''),
                'city': portal_lead.get('city', ''),
                'team_id': team_id,
                'preferred_branch': normalized_city,  # Store normalized city in preferred_branch field
            }
            
            # Create the lead with proper team assignment
            try:
                new_lead = self.env['crm.lead'].create(lead_values)
                
                # Log the sync
                self.env['lead.sync.log'].create({
                    'external_id': portal_lead.get('external_id', ''),
                    'lead_id': new_lead.id,
                })
                
                _logger.info(f"Lead created: {new_lead.name}, assigned to team: {new_lead.team_id.name}, preferred branch: {normalized_city}")
            except Exception as e:
                _logger.error(f"Error creating lead: {e}")
        
        _logger.info("Lead sync completed")

    def _is_lead_already_imported(self, external_id):
        """Check if lead is already imported by external_id"""
        return bool(self.env['lead.sync.log'].search_count([
            ('external_id', '=', external_id)
        ]))

    def _get_portal_leads_data(self):
        """Placeholder method to get lead data - replace with actual API call"""
        # This is just a placeholder - implement your actual API call here
        return []
