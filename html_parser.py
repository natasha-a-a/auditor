"""
HTML Parser module with CachedSoup wrapper for BeautifulSoup.
Provides caching and additional helper methods for common HTML parsing tasks.
"""

from bs4 import BeautifulSoup
import re


class CachedSoup:
    """
    Wrapper around BeautifulSoup that provides caching and helper methods.
    
    This class wraps a BeautifulSoup object and adds:
    - Cached text extraction (text_lower)
    - Helper methods for common checks (viewport, contact forms, analytics, etc.)
    """
    
    def __init__(self, html_content):
        """Initialize with HTML content."""
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self._text_lower = None
    
    @property
    def text_lower(self):
        """Get the lowercase text of the document (cached)."""
        if self._text_lower is None:
            self._text_lower = self.soup.get_text().lower()
        return self._text_lower
    
    def has_viewport(self):
        """Check if the page has a viewport meta tag for mobile responsiveness."""
        viewport = self.soup.find("meta", attrs={"name": "viewport"})
        return viewport is not None
    
    def check_contact_form(self):
        """
        Check for contact forms on the page.
        
        Returns:
            dict with:
                - has_contact_form: bool
                - count: int (number of contact forms found)
                - contact_forms: list of form elements
        """
        forms = self.soup.find_all("form")
        contact_forms = []
        
        # Common contact form indicators
        contact_indicators = [
            "contact", "email", "message", "name", "phone", "tel",
            "subject", "inquiry", "form", "submit", "send"
        ]
        
        for form in forms:
            form_text = form.get_text().lower()
            form_id = form.get("id", "").lower()
            form_class = form.get("class", "").lower()
            form_action = form.get("action", "").lower()
            
            # Check if form contains contact-related elements
            inputs = form.find_all("input")
            has_contact_input = any(
                inp.get("type", "").lower() in ["email", "text", "tel", "textarea"] or
                inp.get("name", "").lower() in contact_indicators or
                inp.get("id", "").lower() in contact_indicators
                for inp in inputs
            )
            
            # Check form attributes and text
            all_text = f"{form_text} {form_id} {form_class} {form_action}"
            is_contact_form = any(
                indicator in all_text
                for indicator in contact_indicators
            )
            
            if is_contact_form or has_contact_input:
                contact_forms.append(form)
        
        return {
            "has_contact_form": len(contact_forms) > 0,
            "count": len(contact_forms),
            "contact_forms": contact_forms
        }
    
    def has_analytics(self):
        """Check if the page has analytics tracking scripts."""
        # Check for common analytics patterns
        analytics_patterns = [
            r'google\-analytics\.com',
            r'googletagmanager\.com',
            r'UA\-\d+',
            r'G\-\w+',
            r"gtag\('",
            r'gtag\(',
            r'ga\.js',
            r'analytics\.js',
            r'segment\.com',
            r'hotjar\.com',
            r'heap\.io',
            r'mixpanel\.com',
            r'piwik\.php',
            r'matomo\.php',
        ]
        
        # Check in script tags
        scripts = self.soup.find_all("script")
        for script in scripts:
            script_src = script.get("src", "")
            script_content = script.string or ""
            for pattern in analytics_patterns:
                if re.search(pattern, script_src, re.IGNORECASE):
                    return True
                if re.search(pattern, script_content, re.IGNORECASE):
                    return True
        
        # Check in noscript tags
        noscripts = self.soup.find_all("noscript")
        for noscript in noscripts:
            if any(re.search(p, noscript.string or "", re.IGNORECASE) for p in analytics_patterns):
                return True
        
        return False
    
    @property
    def scripts(self):
        """Get all script tags."""
        return self.soup.find_all("script")
    
    @property
    def links(self):
        """Get all link tags (a, link, etc.) - returns all anchor tags."""
        return self.soup.find_all("a", href=True)
    
    # Delegate other BeautifulSoup methods to the underlying soup object
    def find(self, *args, **kwargs):
        return self.soup.find(*args, **kwargs)
    
    def find_all(self, *args, **kwargs):
        return self.soup.find_all(*args, **kwargs)
    
    def get_text(self):
        return self.soup.get_text()
    
    @property
    def title(self):
        return self.soup.title
    
    def __getattr__(self, name):
        """Delegate any other attributes to the underlying BeautifulSoup object."""
        return getattr(self.soup, name)
