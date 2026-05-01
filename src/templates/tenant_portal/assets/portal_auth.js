/**
 * Shared authentication and navigation logic for Tenant Portal
 */

(function() {
    const accessToken = localStorage.getItem('tenant_access_token');
    const userRole = localStorage.getItem('tenant_type') || 'marketing'; // root, admin, marketing
    const tenantId = window.location.pathname.split('/')[2];
    
    // Default view state for admins/root
    let activeView = localStorage.getItem('portal_active_view');
    
    // Safety check: marketing users should never have 'admin' view active
    if (userRole === 'marketing') {
        activeView = 'marketing';
    } else if (!activeView) {
        activeView = 'admin';
    }

    function initPortal() {
        if (!accessToken) {
            window.location.href = '/portal/login';
            return;
        }

        // Update page title if on templates page and in marketing view
        if (activeView === 'marketing' && window.location.pathname.includes('/templates')) {
            const h1 = document.querySelector('h1');
            const pageHeaderP = document.querySelector('.page-header p');
            if (h1) h1.textContent = 'Templates';
            if (pageHeaderP) pageHeaderP.textContent = 'Manage your notification templates';
        }

        // Apply active view class to body for CSS-based toggling
        document.body.classList.add('active-view-' + activeView);
        document.body.classList.add('user-role-' + userRole);

        // Inject View Switcher (Admin/Root can toggle, Marketing just sees their role)
        injectViewSwitcher();

        // Auto-redirect marketing users if they are on the main dashboard
        const currentPath = window.location.pathname;
        if (activeView === 'marketing' && (currentPath.endsWith('/dashboard') || currentPath.endsWith('/dashboard/'))) {
            window.location.href = `/portal/${tenantId}/marketing-dashboard`;
            return;
        }

        // Update nav links and visibility
        updateNavigation();
        
        // Handle Logout (any button with class btn-logout or id containing logout)
        const logoutButtons = document.querySelectorAll('.btn-logout, [id*="logoutBtn"], [id*="LogoutBtn"]');
        logoutButtons.forEach(btn => {
            btn.onclick = () => {
                localStorage.clear();
                document.cookie = 'tenant_access_token=; path=/; max-age=0; SameSite=Lax';
                window.location.href = '/portal/login';
            };
        });

        // Set Identity
        const tenantNameEl = document.getElementById('tenantName');
        const tenantIdEl = document.getElementById('tenantIdLabel') || document.getElementById('tenantId');
        if (tenantNameEl) {
            tenantNameEl.textContent = localStorage.getItem('tenant_name') || tenantId;
        }
        if (tenantIdEl && tenantIdEl.tagName !== 'INPUT') {
            tenantIdEl.textContent = tenantId;
        }
    }

    function injectViewSwitcher() {
        const target = document.querySelector('.navbar-user');
        const header = document.querySelector('header');
        
        if (!target && !header) return;

        // Remove existing switcher if any
        const existing = document.querySelector('.view-switcher, .view-switcher-glass');
        if (existing) existing.remove();

        const switcher = document.createElement('div');
        switcher.className = 'view-switcher-glass';
        switcher.style.cssText = 'display: flex; align-items: center; margin-right: 20px; position: relative; z-index: 1000;';
        
        if (userRole === 'root' || userRole === 'admin') {
            const currentLabel = activeView === 'admin' ? 'Admin Portal' : 'Marketing Hub';
            switcher.innerHTML = `
                <div id="viewSwitcherContainer" style="display: flex; align-items: center; gap: 10px; background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 6px 18px; border-radius: 30px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); position: relative; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; user-select: none; min-width: 160px;">
                    <span style="font-size: 9px; font-weight: 800; text-transform: uppercase; opacity: 0.6; color: white; letter-spacing: 1.2px; white-space: nowrap; pointer-events: none;">View</span>
                    <span id="currentViewLabel" style="color: white; font-size: 13px; font-weight: 600; flex-grow: 1; text-align: left;">${currentLabel}</span>
                    <span id="viewSwitcherArrow" style="font-size: 10px; pointer-events: none; color: white; opacity: 0.7; transition: transform 0.3s;">▼</span>
                    
                    <div id="viewSwitcherMenu" style="display: none; position: absolute; top: calc(100% + 10px); left: 0; right: 0; background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 16px; overflow: hidden; box-shadow: 0 15px 35px rgba(0,0,0,0.3); z-index: 10001; transform-origin: top center;">
                        <div class="view-option" data-value="admin" style="padding: 12px 18px; color: white; font-size: 13px; font-weight: 500; transition: all 0.2s; border-bottom: 1px solid rgba(255, 255, 255, 0.05); display: flex; align-items: center; justify-content: space-between;">
                            Admin Portal
                            ${activeView === 'admin' ? '<span style="color: #6366f1;">●</span>' : ''}
                        </div>
                        <div class="view-option" data-value="marketing" style="padding: 12px 18px; color: white; font-size: 13px; font-weight: 500; transition: all 0.2s; display: flex; align-items: center; justify-content: space-between;">
                            Marketing Hub
                            ${activeView === 'marketing' ? '<span style="color: #6366f1;">●</span>' : ''}
                        </div>
                    </div>
                </div>
                <style>
                    .view-option:hover { background: rgba(255, 255, 255, 0.15) !important; padding-left: 22px !important; }
                    #viewSwitcherContainer:hover { background: rgba(255, 255, 255, 0.15); transform: translateY(-1px); }
                    #viewSwitcherContainer.active #viewSwitcherArrow { transform: rotate(180deg); }
                </style>
            `;
        } else {
            // High-quality glass effect role switcher for marketing users (with single option)
            switcher.innerHTML = `
                <div id="viewSwitcherContainer" style="display: flex; align-items: center; gap: 10px; background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); border: 1px solid rgba(255, 255, 255, 0.2); padding: 6px 18px; border-radius: 30px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); position: relative; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; user-select: none; min-width: 160px;">
                    <span style="font-size: 9px; font-weight: 800; text-transform: uppercase; opacity: 0.6; color: white; letter-spacing: 1.2px; white-space: nowrap; pointer-events: none;">Role</span>
                    <span id="currentViewLabel" style="color: white; font-size: 13px; font-weight: 600; flex-grow: 1; text-align: left;">Marketing Hub</span>
                    <span id="viewSwitcherArrow" style="font-size: 10px; pointer-events: none; color: white; opacity: 0.7; transition: transform 0.3s;">▼</span>
                    
                    <div id="viewSwitcherMenu" style="display: none; position: absolute; top: calc(100% + 10px); left: 0; right: 0; background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 16px; overflow: hidden; box-shadow: 0 15px 35px rgba(0,0,0,0.3); z-index: 10001; transform-origin: top center;">
                        <div class="view-option" data-value="marketing" style="padding: 12px 18px; color: white; font-size: 13px; font-weight: 500; transition: all 0.2s; display: flex; align-items: center; justify-content: space-between;">
                            Marketing Hub
                            <span style="color: #6366f1;">●</span>
                        </div>
                    </div>
                </div>
                <style>
                    .view-option:hover { background: rgba(255, 255, 255, 0.15) !important; padding-left: 22px !important; }
                    #viewSwitcherContainer:hover { background: rgba(255, 255, 255, 0.15); transform: translateY(-1px); }
                    #viewSwitcherContainer.active #viewSwitcherArrow { transform: rotate(180deg); }
                </style>
            `;
        }

        if (target) {
            const userInfo = target.querySelector('.user-info');
            const logoutBtn = document.getElementById('logoutBtn');
            if (userInfo) {
                target.insertBefore(switcher, userInfo);
            } else if (logoutBtn) {
                target.insertBefore(switcher, logoutBtn);
            } else {
                target.appendChild(switcher);
            }
        } else if (header) {
            const navUser = header.querySelector('.navbar-user');
            const info = header.querySelector('.user-info') || header.querySelector('div:last-child');
            if (navUser) {
                navUser.insertBefore(switcher, navUser.firstChild);
            } else if (info) {
                header.insertBefore(switcher, info);
            } else {
                header.appendChild(switcher);
            }
        }

        // Logic for custom dropdown
        const container = document.getElementById('viewSwitcherContainer');
        const menu = document.getElementById('viewSwitcherMenu');
        
        if (container && menu) {
            container.onclick = (e) => {
                e.stopPropagation();
                const isOpen = menu.style.display === 'block';
                menu.style.display = isOpen ? 'none' : 'block';
                container.classList.toggle('active', !isOpen);
            };

            document.querySelectorAll('.view-option').forEach(opt => {
                opt.onclick = (e) => {
                    e.stopPropagation();
                    const newView = opt.getAttribute('data-value');
                    if (newView === activeView) {
                        menu.style.display = 'none';
                        container.classList.remove('active');
                        return;
                    }

                    localStorage.setItem('portal_active_view', newView);
                    
                    // Force redirection to landing pages on view switch
                    if (newView === 'marketing') {
                        window.location.href = `/portal/${tenantId}/marketing-dashboard`;
                    } else {
                        window.location.href = `/portal/${tenantId}/dashboard`;
                    }
                };
            });

            // Close on outside click
            window.addEventListener('click', () => {
                menu.style.display = 'none';
                container.classList.remove('active');
            });
        }
    }

    function updateNavigation() {
        const navLinks = document.querySelector('.navbar-links') || document.querySelector('.nav-links');
        if (!navLinks) return;

        // Branding link
        const brands = document.querySelectorAll('.navbar-brand');
        brands.forEach(brand => {
            const targetPath = (activeView === 'marketing') ? 'marketing-dashboard' : 'dashboard';
            const href = `/portal/${tenantId}/${targetPath}`;
            
            if (brand.tagName === 'A') {
                brand.href = href;
            } else {
                brand.style.cursor = 'pointer';
                brand.onclick = () => window.location.href = href;
            }
        });

        // Ensure Team link exists for admins/root if not in HTML
        if (activeView === 'admin' && (userRole === 'admin' || userRole === 'root') && !document.getElementById('navTeam')) {
            const teamLink = document.createElement('a');
            teamLink.id = 'navTeam';
            teamLink.href = `/portal/${tenantId}/team`;
            teamLink.textContent = 'Team Management';
            // Insert before Profile if possible, otherwise at end
            const profileLink = document.getElementById('navProfile');
            if (profileLink) {
                navLinks.insertBefore(teamLink, profileLink);
            } else {
                navLinks.appendChild(teamLink);
            }
        }

        // Current links from HTML or newly injected
        const links = {
            marketingDashboard: document.getElementById('navMarketingDashboard'),
            dashboard: document.getElementById('navDashboard'),
            templates: document.getElementById('navTemplates'),
            analytics: document.getElementById('navAnalytics'),
            channels: document.getElementById('navChannels'),
            developer: document.getElementById('navDeveloper'),
            team: document.getElementById('navTeam'),
            profile: document.getElementById('navProfile')
        };

        // Wire hrefs
        if (links.marketingDashboard) links.marketingDashboard.href = `/portal/${tenantId}/marketing-dashboard`;
        if (links.dashboard) links.dashboard.href = `/portal/${tenantId}/dashboard`;
        if (links.templates) links.templates.href = `/portal/${tenantId}/templates`;
        if (links.analytics) links.analytics.href = `/portal/${tenantId}/analytics`;
        if (links.channels) links.channels.href = `/portal/${tenantId}/channels`;
        if (links.developer) links.developer.href = `/portal/${tenantId}/developer`;
        if (links.team) links.team.href = `/portal/${tenantId}/team`;
        if (links.profile) links.profile.href = `/portal/${tenantId}/profile`;

        // Hide links based on view/role
        if (activeView === 'marketing') {
            if (links.marketingDashboard) {
                links.marketingDashboard.style.display = 'inline-block';
                links.marketingDashboard.textContent = 'Dashboard';
            }
            if (links.analytics) links.analytics.style.display = 'none';
            if (links.channels) links.channels.style.display = 'none';
            if (links.developer) links.developer.style.display = 'none';
            if (links.team) links.team.style.display = 'none';
            if (links.profile) links.profile.style.display = 'none';
            
            // Rename Dashboard to Send Messages for marketing view
            if (links.dashboard) {
                links.dashboard.textContent = 'Send Messages';
                links.dashboard.href = `/portal/${tenantId}/marketing`;
            }
        } else {
            if (links.marketingDashboard) links.marketingDashboard.style.display = 'none';
            // Admin view - hide Team if not root/admin (extra safety)
            if (userRole === 'marketing') {
                if (links.team) links.team.style.display = 'none';
                if (links.channels) links.channels.style.display = 'none';
                if (links.developer) links.developer.style.display = 'none';
            }

            // Rename "Team" to "Team Management" when on admin pages
            const currentPath = window.location.pathname;
            const targetPages = ['/dashboard', '/templates', '/analytics', '/channels', '/developer', '/profile', '/team'];
            if (links.team && targetPages.some(page => currentPath.includes(page))) {
                links.team.textContent = 'Team Management';
            }
        }
    }

    // Run on load
    window.addEventListener('DOMContentLoaded', initPortal);
})();
