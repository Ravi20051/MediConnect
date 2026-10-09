/**
 * MediConnect — ASHA Field Companion Application Logic
 * Field-oriented, offline-first EHR & predictive support system.
 */

const app = {
  currentUser: null,
  isOnline: true,
  simulatedOffline: false,
  isSyncing: false,
  currentSyncStatus: 'ONLINE',
  syncRetryInterval: null,
  offlineQueue: {
    patients: [],
    maternal_records: [],
    children: [],
    immunizations: [],
    symptoms: []
  },
  cachedData: {
    patients: [],
    children: [],
    followups: [],
    alerts: [],
    stats: null
  },

  // 1. Initialization
  init() {
    this.registerServiceWorker();
    this.loadOfflineQueue();
    this.checkStoredAuth();
    this.setupEventListeners();
    this.setupNetworkMonitoring();

    if (window.i18n) {
      window.i18n.applyTranslations();
    }

    if (this.currentUser) {
      this.updateUserUI();
      this.showView('dashboard');
      this.loadDashboardData();
    } else {
      this.showView('login');
    }

    // Phase 2: Safe background auto-sync retry every 30 seconds while open and online
    if (this.syncRetryInterval) clearInterval(this.syncRetryInterval);
    this.syncRetryInterval = setInterval(() => {
      if (this.isOnline && this.getPendingQueueCount() > 0 && !this.isSyncing) {
        this.syncPendingRecords();
      }
    }, 30000);

    // On application startup: if online, automatically attempt pending synchronization
    if (this.isOnline && this.getPendingQueueCount() > 0) {
      this.syncPendingRecords();
    } else {
      this.setSyncStatus(this.isOnline ? 'ONLINE' : 'OFFLINE');
    }
  },

  registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { scope: '/' })
          .then(reg => {
            console.log('[SW] ServiceWorker registered with scope:', reg.scope);
          })
          .catch(err => {
            console.warn('[SW] ServiceWorker registration notice:', err.message);
          });
      });
    }
  },

  async apiFetch(url, options = {}) {
    options = options || {};
    options.headers = options.headers || {};
    const token = localStorage.getItem('mc_token');
    if (token) {
      if (typeof options.headers === 'object' && !Array.isArray(options.headers)) {
        if (!options.headers['Authorization']) {
          options.headers['Authorization'] = `Bearer ${token}`;
        }
      }
    }
    return fetch(url, options);
  },

  // 2. Authentication
  checkStoredAuth() {
    const stored = localStorage.getItem('mc_user');
    if (stored) {
      try {
        this.currentUser = JSON.parse(stored);
      } catch (e) {
        this.currentUser = null;
      }
    } else {
      this.currentUser = null;
    }

    // Restore remembered username if present
    const remembered = localStorage.getItem('mc_remembered_username');
    const uField = document.getElementById('loginUsername');
    const remBox = document.getElementById('loginRememberMe');
    if (uField && remembered) {
      uField.value = remembered;
      if (remBox) remBox.checked = true;
    }
  },

  updateUserUI() {
    if (!this.currentUser) return;
    const headerName = document.getElementById('headerUserName');
    const headerVillage = document.getElementById('headerUserVillage');
    const dashName = document.getElementById('dashAshaName');
    const dashVillage = document.getElementById('dashVillage');
    const dashCenter = document.getElementById('dashSubCenter');

    const vName = this.currentUser.village || 'Field';
    if (headerName) headerName.textContent = this.currentUser.full_name || this.currentUser.username;
    if (headerVillage) headerVillage.textContent = `Village: ${vName}`;
    if (dashName) dashName.textContent = this.currentUser.full_name || this.currentUser.username;
    if (dashVillage) dashVillage.textContent = vName;
    if (dashCenter) dashCenter.textContent = this.currentUser.sub_center || `${vName} Sub-Center`;
  },

  showAuthAlert(formType, message, type = 'error') {
    const banner = document.getElementById(`${formType}AlertBanner`);
    const msgEl = document.getElementById(`${formType}AlertMsg`);
    const iconEl = document.getElementById(`${formType}AlertIcon`);
    if (!banner || !msgEl) return;
    banner.className = `auth-alert ${type}`;
    msgEl.textContent = message;
    if (iconEl) iconEl.textContent = type === 'success' ? '✅' : '⚠️';
    banner.style.display = 'flex';
  },

  hideAuthAlert(formType) {
    const banner = document.getElementById(`${formType}AlertBanner`);
    if (banner) banner.style.display = 'none';
  },

  devQuickFill(username, password) {
    const u = document.getElementById('loginUsername');
    const p = document.getElementById('loginPassword');
    if (u) u.value = username;
    if (p) p.value = password;
    this.hideAuthAlert('login');
    const btn = document.getElementById('btnSubmitLogin');
    if (btn) btn.focus();
  },

  setupPasswordToggles() {
    const pairs = [
      { btnId: 'loginPwdToggle', inputId: 'loginPassword' },
      { btnId: 'regPwdToggle', inputId: 'regPassword' },
      { btnId: 'regConfirmPwdToggle', inputId: 'regConfirmPassword' }
    ];

    pairs.forEach(({ btnId, inputId }) => {
      const btn = document.getElementById(btnId);
      const input = document.getElementById(inputId);
      if (btn && input && !btn.dataset.toggleBound) {
        btn.dataset.toggleBound = 'true';
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          const isPassword = input.type === 'password';
          input.type = isPassword ? 'text' : 'password';
          const eye = btn.querySelector('.eye-text');
          if (eye) eye.textContent = isPassword ? '🙈' : '👁️';
        });
      }
    });
  },

  async handleLogin(e) {
    e.preventDefault();
    this.hideAuthAlert('login');

    const username = document.getElementById('loginUsername')?.value.trim();
    const password = document.getElementById('loginPassword')?.value;
    const rememberMe = document.getElementById('loginRememberMe')?.checked;

    if (!username || !password) {
      this.showAuthAlert('login', 'Please enter both username and password.');
      return;
    }

    const btn = document.getElementById('btnSubmitLogin');
    const spinner = document.getElementById('loginSpinner');
    const arrow = document.getElementById('loginArrow');
    const text = document.getElementById('btnTextLogin');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (arrow) arrow.style.display = 'none';
    if (text) text.textContent = 'Signing in...';

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        this.showAuthAlert('login', err.detail || 'Invalid username or password. Please verify credentials.');
        return;
      }

      const data = await res.json();
      this.currentUser = data.user;
      localStorage.setItem('mc_user', JSON.stringify(this.currentUser));
      localStorage.setItem('mc_token', data.token);

      if (rememberMe) {
        localStorage.setItem('mc_remembered_username', username);
      } else {
        localStorage.removeItem('mc_remembered_username');
      }

      this.updateUserUI();
      this.showView('dashboard');
      this.loadDashboardData();
    } catch (err) {
      // Offline fallback login for known cached field workers
      if (username === 'asha_sunita' || username === 'asha_anita') {
        this.currentUser = {
          id: username === 'asha_sunita' ? 1 : 2,
          username: username,
          full_name: username === 'asha_sunita' ? 'Sunita Devi' : 'Anita Sharma',
          role: 'asha_worker',
          village: username === 'asha_sunita' ? 'Rampur' : 'Bhimpur',
          sub_center: username === 'asha_sunita' ? 'Rampur Sub-Center' : 'Bhimpur Sub-Center'
        };
        localStorage.setItem('mc_user', JSON.stringify(this.currentUser));
        this.updateUserUI();
        this.showView('dashboard');
        this.loadDashboardData();
      } else {
        this.showAuthAlert('login', 'Network connection unavailable. Please connect online to authenticate.');
      }
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (arrow) arrow.style.display = 'inline-block';
      if (text) text.textContent = 'Sign In';
    }
  },

  async handleSignup(e) {
    e.preventDefault();
    this.hideAuthAlert('signup');

    const fullName = document.getElementById('regFullName')?.value.trim();
    const username = document.getElementById('regUsername')?.value.trim();
    const village = document.getElementById('regVillage')?.value.trim();
    const subCenter = document.getElementById('regSubCenter')?.value.trim();
    const phone = document.getElementById('regPhone')?.value.trim();
    const password = document.getElementById('regPassword')?.value;
    const confirmPassword = document.getElementById('regConfirmPassword')?.value;

    if (!fullName || !username || !village || !subCenter || !password) {
      this.showAuthAlert('signup', 'Please fill in all required fields.');
      return;
    }

    if (password.length < 6) {
      this.showAuthAlert('signup', 'Password must be at least 6 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      this.showAuthAlert('signup', 'Passwords do not match. Please verify.');
      document.getElementById('regConfirmPassword')?.focus();
      return;
    }

    const btn = document.getElementById('btnSubmitSignup');
    const spinner = document.getElementById('signupSpinner');
    const arrow = document.getElementById('signupArrow');
    const text = document.getElementById('btnTextSignup');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (arrow) arrow.style.display = 'none';
    if (text) text.textContent = 'Creating Account...';

    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName,
          username: username,
          password: password,
          village: village,
          sub_center: subCenter,
          phone: phone
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        this.showAuthAlert('signup', err.detail || 'Registration failed. Please check inputs.');
        return;
      }

      const data = await res.json();
      
      // Successfully registered! Transition to login with prefilled username
      document.getElementById('signupForm')?.reset();
      this.showView('login');
      const loginUserInput = document.getElementById('loginUsername');
      if (loginUserInput) loginUserInput.value = username;
      const loginPwdInput = document.getElementById('loginPassword');
      if (loginPwdInput) {
        loginPwdInput.value = '';
        loginPwdInput.focus();
      }
      this.showAuthAlert('login', data.message || 'Account registered successfully! You can now sign in.', 'success');
    } catch (err) {
      this.showAuthAlert('signup', 'Network connection error. Please verify server connectivity.');
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (arrow) arrow.style.display = 'inline-block';
      if (text) text.textContent = 'Create Field Account';
    }
  },

  logout() {
    localStorage.removeItem('mc_user');
    localStorage.removeItem('mc_token');
    localStorage.removeItem('mc_cached_stats');
    localStorage.removeItem('mc_last_sync_time');
    this.currentUser = null;
    this.cachedData = {
      patients: [],
      children: [],
      followups: [],
      alerts: [],
      stats: null
    };
    this.showView('login');
  },

  // 3. Navigation
  showView(viewName, options = {}) {
    document.querySelectorAll('.view-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

    const navBar = document.getElementById('mainNavBar');
    const userBadge = document.getElementById('userBadge');
    const cleanBtn = document.getElementById('cleanRecordsBtn');
    const logoutBtn = document.getElementById('logoutBtn');

    if (viewName === 'login' || viewName === 'signup') {
      if (navBar) navBar.style.display = 'none';
      if (userBadge) userBadge.style.display = 'none';
      if (cleanBtn) cleanBtn.style.display = 'none';
      if (logoutBtn) logoutBtn.style.display = 'none';
      this.hideAuthAlert(viewName);
    } else {
      if (navBar) navBar.style.display = '';
      if (userBadge) userBadge.style.display = 'flex';
      if (cleanBtn) cleanBtn.style.display = 'inline-flex';
      if (logoutBtn) logoutBtn.style.display = 'inline-flex';
    }

    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) {
      targetView.classList.add('active');
    }

    const targetTab = document.querySelector(`.nav-tab[data-view="${viewName}"]`);
    if (targetTab) {
      targetTab.classList.add('active');
    }

    // Trigger view-specific loads
    switch (viewName) {
      case 'dashboard':
        this.loadDashboardData();
        break;
      case 'mothers':
        this.loadMothers(options.filterHighRisk);
        break;
      case 'maternal-predict':
        this.prepareMaternalPredictView();
        break;
      case 'children':
        this.loadChildren();
        break;
      case 'add-child':
        this.populateMotherSelectForChild();
        break;
      case 'immunization-followup':
        this.loadImmunizationFollowUp();
        break;
      case 'outbreak-alerts':
        this.loadOutbreakAlerts();
        break;
      case 'symptom-entry':
        document.getElementById('symOnsetDate').value = new Date().toISOString().split('T')[0];
        break;
      case 'sync-center':
        this.updateSyncCenterUI();
        break;
      case 'model-status':
        this.loadModelStatus();
        break;
      case 'reports':
        this.loadCoverageReports();
        break;
    }
  },

  // 4. Network Monitoring & Simulation
  setupNetworkMonitoring() {
    window.addEventListener('online', () => {
      this.handleNetworkChange(true);
      this.syncPendingRecords();
    });
    window.addEventListener('offline', () => {
      this.handleNetworkChange(false);
    });
    
    document.getElementById('toggleNetworkBtn').addEventListener('click', () => {
      this.simulatedOffline = !this.simulatedOffline;
      const effectiveOnline = !this.simulatedOffline && navigator.onLine;
      this.handleNetworkChange(effectiveOnline);
      if (effectiveOnline && this.getPendingQueueCount() > 0) {
        this.syncPendingRecords();
      }
    });

    const initialOnline = navigator.onLine && !this.simulatedOffline;
    this.handleNetworkChange(initialOnline);
  },

  handleNetworkChange(online) {
    this.isOnline = online;
    const toggleBtn = document.getElementById('toggleNetworkBtn');

    if (online) {
      if (toggleBtn) {
        toggleBtn.textContent = window.i18n ? window.i18n.get('btn_sim_offline') : 'Simulate Offline';
        toggleBtn.style.background = 'transparent';
      }
      if (this.getPendingQueueCount() > 0) {
        this.setSyncStatus('PENDING SYNC');
      } else {
        this.setSyncStatus('ONLINE');
      }
    } else {
      if (toggleBtn) {
        toggleBtn.textContent = window.i18n ? window.i18n.get('btn_reconnect_online') : 'Re-Connect Online';
        toggleBtn.style.background = '#991B1B';
      }
      this.setSyncStatus('OFFLINE');
    }
  },

  setSyncStatus(status) {
    this.currentSyncStatus = status; // ONLINE, OFFLINE, PENDING SYNC, SYNCING..., SYNCED, SYNC FAILED — RETRYING
    const count = this.getPendingQueueCount();

    const pill = document.getElementById('networkPill');
    const text = document.getElementById('networkText');
    if (pill && text) {
      if (status === 'OFFLINE') {
        pill.className = 'network-pill offline';
        text.textContent = count > 0 ? `Offline (${count} Pending)` : 'Offline';
      } else if (status === 'SYNCING...') {
        pill.className = 'network-pill syncing';
        text.textContent = 'Syncing...';
      } else if (status === 'SYNC FAILED — RETRYING') {
        pill.className = 'network-pill retry';
        text.textContent = `Sync Failed — Retrying (${count})`;
      } else if (status === 'PENDING SYNC') {
        pill.className = 'network-pill pending';
        text.textContent = `Pending Sync (${count})`;
      } else if (status === 'SYNCED') {
        pill.className = 'network-pill online';
        text.textContent = 'Synced';
      } else {
        pill.className = 'network-pill online';
        text.textContent = 'Online';
      }
    }

    const stateEl = document.getElementById('syncNetworkState');
    if (stateEl) {
      stateEl.textContent = status;
      if (status === 'OFFLINE') stateEl.style.color = 'var(--risk-high)';
      else if (status === 'SYNCING...') stateEl.style.color = '#B45309';
      else if (status === 'SYNC FAILED — RETRYING') stateEl.style.color = '#B91C1C';
      else if (status === 'PENDING SYNC') stateEl.style.color = '#D97706';
      else if (status === 'SYNCED' || status === 'ONLINE') stateEl.style.color = '#047857';
    }

    const syncBtn = document.getElementById('syncNowBtn');
    if (syncBtn) {
      syncBtn.disabled = (status === 'SYNCING...');
      syncBtn.textContent = (status === 'SYNCING...') ? 'Syncing...' : 'Sync Now';
    }

    this.updatePendingBadges();
  },

  // 5. Offline Queue Management
  loadOfflineQueue() {
    const saved = localStorage.getItem('mc_offline_queue');
    if (saved) {
      try {
        this.offlineQueue = JSON.parse(saved);
      } catch (e) {
        this.offlineQueue = { patients: [], maternal_records: [], children: [], immunizations: [], symptoms: [] };
      }
    }
    this.updatePendingBadges();
  },

  saveOfflineQueue() {
    localStorage.setItem('mc_offline_queue', JSON.stringify(this.offlineQueue));
    this.updatePendingBadges();
  },

  getPendingQueueCount() {
    return (
      (this.offlineQueue.patients || []).length +
      (this.offlineQueue.maternal_records || []).length +
      (this.offlineQueue.children || []).length +
      (this.offlineQueue.immunizations || []).length +
      (this.offlineQueue.symptoms || []).length
    );
  },

  updatePendingBadges() {
    const count = this.getPendingQueueCount();
    const navBadge = document.getElementById('navSyncBadge');
    if (navBadge) {
      navBadge.textContent = count;
      navBadge.style.background = count > 0 ? 'var(--terracotta)' : '#555';
    }
    const syncCountEl = document.getElementById('syncPendingCount');
    if (syncCountEl) {
      syncCountEl.textContent = count;
    }
  },

  async syncPendingRecords() {
    // Prevent duplicate simultaneous sync requests with sync lock
    if (this.isSyncing) {
      console.log("[Sync] Sync already in progress. Skipping duplicate request.");
      return;
    }

    const count = this.getPendingQueueCount();
    if (count === 0) {
      if (this.isOnline) {
        this.setSyncStatus('SYNCED');
      }
      return;
    }

    if (!this.isOnline || (navigator && !navigator.onLine) || this.simulatedOffline) {
      this.setSyncStatus('OFFLINE');
      return;
    }

    this.isSyncing = true;
    this.setSyncStatus('SYNCING...');

    try {
      const payload = {
        client_device_id: "ASHA-TAB-VILLAGE",
        user_id: this.currentUser ? this.currentUser.id : 1,
        patients: [...this.offlineQueue.patients],
        maternal_records: [...this.offlineQueue.maternal_records],
        children: [...this.offlineQueue.children],
        immunizations: [...this.offlineQueue.immunizations],
        symptoms: [...this.offlineQueue.symptoms]
      };

      const res = await this.apiFetch('/api/sync/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`Sync server responded with HTTP ${res.status}`);
      }

      const result = await res.json();
      if (!result.success) {
        throw new Error(result.error || "Sync rejected by server");
      }

      // Never delete pending local records before successful server confirmation
      this.offlineQueue = { patients: [], maternal_records: [], children: [], immunizations: [], symptoms: [] };
      this.saveOfflineQueue();

      localStorage.setItem('mc_last_sync_time', result.synced_at);
      this.setSyncStatus('SYNCED');

      this.loadDashboardData();
      this.updateSyncCenterUI();
    } catch (err) {
      // If sync fails: keep record locally, preserve client_uid, show pending/retry state
      console.warn("[Sync] Synchronization failed; records remain safely stored locally for retry:", err.message);
      this.setSyncStatus('SYNC FAILED — RETRYING');
    } finally {
      this.isSyncing = false;
      this.updateSyncCenterUI();
    }
  },

  async triggerSync() {
    return this.syncPendingRecords();
  },

  updateSyncCenterUI() {
    this.updatePendingBadges();
    const lastSync = localStorage.getItem('mc_last_sync_time');
    const lastTimeEl = document.getElementById('syncLastTime');
    if (lastTimeEl) {
      lastTimeEl.textContent = lastSync ? new Date(lastSync).toLocaleString() : 'Never';
    }

    const tbody = document.getElementById('offlineQueueTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const allItems = [];
    this.offlineQueue.patients.forEach(p => allItems.push({ type: 'Mother / Patient', id: p.client_uid, summary: `${p.full_name} (${p.village})`, time: p.created_at }));
    this.offlineQueue.children.forEach(c => allItems.push({ type: 'Child Record', id: c.client_uid, summary: `${c.name} (${c.village})`, time: c.created_at }));
    this.offlineQueue.symptoms.forEach(s => allItems.push({ type: 'Symptom Log', id: s.client_uid, summary: `${s.symptom_type} - ${s.person_name} (${s.village})`, time: s.recorded_at }));
    this.offlineQueue.immunizations.forEach(i => allItems.push({ type: 'Vaccine Given', id: i.client_uid, summary: `${i.vaccine_name} administered on ${i.given_date}`, time: i.recorded_at }));

    if (allItems.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No pending records in offline queue. All records are synchronized.</td></tr>`;
      return;
    }

    allItems.forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${item.type}</strong></td>
        <td><code>${item.id}</code></td>
        <td>${item.summary}</td>
        <td>${new Date(item.time).toLocaleTimeString()}</td>
        <td><span class="badge badge-due">Pending Sync</span></td>
      `;
      tbody.appendChild(tr);
    });
  },

  // 6. Dashboard Data Loader
  async loadDashboardData() {
    try {
      let stats = null;
      if (this.isOnline) {
        try {
          const res = await this.apiFetch('/api/dashboard/stats');
          if (res.ok) {
            stats = await res.json();
            this.cachedData.stats = stats;
            localStorage.setItem('mc_cached_stats', JSON.stringify(stats));
          }
        } catch (_) {}
      }
      if (!stats) {
        const cached = localStorage.getItem('mc_cached_stats');
        stats = cached ? JSON.parse(cached) : { total_mothers: 0, high_risk_mothers: 0, total_children: 0, immunizations: { due: 0, overdue: 0 }, active_outbreak_alerts: 0 };
      }

      document.getElementById('kpiTotalMothers').textContent = (stats.total_mothers || 0) + (this.offlineQueue.patients || []).length;
      document.getElementById('kpiHighRiskMothers').textContent = stats.high_risk_mothers || 0;
      document.getElementById('kpiTotalChildren').textContent = (stats.total_children || 0) + (this.offlineQueue.children || []).length;
      document.getElementById('kpiPendingVaccines').textContent = ((stats.immunizations ? stats.immunizations.due : 0) + (stats.immunizations ? stats.immunizations.overdue : 0));
      document.getElementById('kpiOutbreakAlerts').textContent = stats.active_outbreak_alerts || 0;
      
      const lastSync = stats.last_synced_at || localStorage.getItem('mc_last_sync_time');
      document.getElementById('kpiLastSync').textContent = lastSync ? `Last: ${new Date(lastSync).toLocaleTimeString()}` : 'Last: Never';

      // Load Urgent Alerts into Banner if any
      const alertContainer = document.getElementById('dashAlertBannerContainer');
      if (stats.active_outbreak_alerts > 0) {
        const vText = this.currentUser?.village || 'the village';
        alertContainer.innerHTML = `
          <div class="alert-box danger" style="cursor:pointer;" onclick="app.showView('outbreak-alerts')">
            <h4>🚨 Urgent Village Health Alert: Unusual Symptom Pattern Detected</h4>
            <p>A recent cluster of acute symptom cases was detected in ${vText}. Click to review field advisory and preventive mobilization.</p>
          </div>
        `;
      } else {
        alertContainer.innerHTML = '';
      }

      // Load Quick Previews on Dashboard
      this.loadDashboardPreviews();
    } catch (e) {
      console.warn("Failed to load live dashboard stats, relying on cache", e);
    }
  },

  async loadDashboardPreviews() {
    // High-risk preview
    try {
      const res = await this.apiFetch('/api/patients?high_risk_only=true');
      const data = await res.json();
      const container = document.getElementById('dashHighRiskList');
      if (data.patients.length === 0) {
        container.innerHTML = `<p class="empty-state">No high-risk maternal cases currently flagged.</p>`;
      } else {
        let html = `<table class="data-table"><thead><tr><th>Mother Name</th><th>Village</th><th>Blood Pressure / Sugar</th><th>Action</th></tr></thead><tbody>`;
        data.patients.slice(0, 3).forEach(p => {
          html += `<tr>
            <td><strong>${p.full_name}</strong> (Age ${p.age})</td>
            <td>${p.village}</td>
            <td><span class="badge badge-high-risk">${p.latest_risk_level || 'High Risk'}</span></td>
            <td><button class="btn btn-outline btn-sm" onclick="app.openMaternalCheckFor('${p.id}', '${p.full_name}', ${p.age})">Check Vitals</button></td>
          </tr>`;
        });
        html += `</tbody></table>`;
        container.innerHTML = html;
      }
    } catch (e) {}

    // Immunization preview
    try {
      const res = await this.apiFetch('/api/immunizations/follow-up');
      const data = await res.json();
      const container = document.getElementById('dashImmunizationList');
      const list = data.follow_up_list || [];
      document.getElementById('navOverdueBadge').textContent = data.summary.overdue_count || 0;

      if (list.length === 0) {
        container.innerHTML = `<p class="empty-state">All child immunizations up to date.</p>`;
      } else {
        let html = `<table class="data-table"><thead><tr><th>Child</th><th>Vaccine Due</th><th>Urgency</th><th>Action</th></tr></thead><tbody>`;
        list.slice(0, 3).forEach(item => {
          const badgeClass = item.urgency === 'HIGH' ? 'badge-overdue' : 'badge-due';
          html += `<tr>
            <td><strong>${item.child_name}</strong> (${item.village})</td>
            <td>${item.vaccine_name} (Dose ${item.dose_number})</td>
            <td><span class="badge ${badgeClass}">${item.urgency_badge}</span></td>
            <td><button class="btn btn-primary btn-sm" onclick="app.openVaccineModal(${item.immunization_id}, '${item.child_name}', '${item.vaccine_name}')">Record Dose</button></td>
          </tr>`;
        });
        html += `</tbody></table>`;
        container.innerHTML = html;
      }
    } catch (e) {}
  },

  // 7. Mothers & Patients
  async loadMothers(highRiskOnly = false) {
    const search = document.getElementById('motherSearchInput').value;
    const village = document.getElementById('motherVillageFilter').value;
    const hrCheck = document.getElementById('motherHighRiskFilter');
    if (highRiskOnly !== undefined) hrCheck.checked = highRiskOnly;

    let url = `/api/patients?`;
    if (village) url += `village=${encodeURIComponent(village)}&`;
    if (search) url += `search=${encodeURIComponent(search)}&`;
    if (hrCheck.checked) url += `high_risk_only=true&`;

    try {
      let patients = [];
      if (this.isOnline) {
        try {
          const res = await this.apiFetch(url);
          if (res.ok) {
            const data = await res.json();
            patients = data.patients || [];
            this.cachedData.patients = patients;
          } else {
            patients = this.cachedData.patients || [];
          }
        } catch (fetchErr) {
          patients = this.cachedData.patients || [];
        }
      } else {
        patients = this.cachedData.patients || [];
      }

      // Merge pending offline patients
      const merged = [...this.offlineQueue.patients, ...patients];
      const tbody = document.getElementById('mothersTableBody');
      tbody.innerHTML = '';

      if (merged.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No maternal records found matching criteria.</td></tr>`;
        return;
      }

      merged.forEach(p => {
        const tr = document.createElement('tr');
        const isHi = window.i18n && window.i18n.currentLang === 'hi';
        const isHigh = p.high_risk_flag == 1 || p.latest_risk_level === 'High Risk';
        const riskBadge = isHigh
          ? `<span class="badge badge-high-risk">${isHi ? 'उच्च जोखिम' : 'High Risk'}</span>`
          : (p.latest_risk_level === 'Medium Risk'
            ? `<span class="badge badge-med-risk">${isHi ? 'मध्यम जोखिम' : 'Medium Risk'}</span>`
            : `<span class="badge badge-low-risk">${isHi ? 'सामान्य / कम जोखिम' : 'Low Risk'}</span>`);

        const isPending = (p.sync_status === 'PENDING_SYNC') || (this.offlineQueue.patients || []).some(x => x.client_uid === p.client_uid);
        const syncBadge = !isPending
          ? `<span class="badge badge-completed" title="${isHi ? 'सर्वर से सिंक किया गया' : 'Synced with server'}">✓ ${isHi ? 'सिंक हुआ' : 'Synced'}</span>`
          : `<span class="badge badge-due" title="${isHi ? 'स्थानीय डिवाइस पर सुरक्षित - लंबित सिंक' : 'Stored locally - Pending Sync'}">⏱ ${isHi ? 'लंबित सिंक' : 'Pending Sync'}</span>`;

        tr.innerHTML = `
          <td><code>${p.rch_id || p.client_uid || 'ID-' + p.id}</code></td>
          <td><strong>${p.full_name}</strong><br><span style="font-size:12px; color:var(--text-muted);">${isHi ? 'पति' : 'Husband'}: ${p.husband_name || '-'}</span></td>
          <td>${p.age} ${isHi ? 'वर्ष' : 'yrs'}</td>
          <td>${p.village}</td>
          <td>${p.phone || '-'}</td>
          <td>${p.edd_date || '-'}</td>
          <td>${riskBadge} ${syncBadge}</td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="app.openMaternalCheckFor('${p.id}', '${p.full_name}', ${p.age})">
              🩺 ${isHi ? 'जांचें' : 'Check Risk'}
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error(e);
    }
  },

  async handleAddMother(e) {
    e.preventDefault();
    const patientData = {
      client_uid: `PAT-LOCAL-${Date.now()}`,
      full_name: document.getElementById('mFullName').value.trim(),
      age: parseInt(document.getElementById('mAge').value),
      husband_name: document.getElementById('mHusbandName').value.trim(),
      village: (this.currentUser && this.currentUser.role === 'asha_worker') ? this.currentUser.village : document.getElementById('mVillage').value,
      phone: document.getElementById('mPhone').value.trim(),
      rch_id: document.getElementById('mRchId').value.trim(),
      lmp_date: document.getElementById('mLmpDate').value || null,
      gravida: parseInt(document.getElementById('mGravida').value) || 1,
      notes: document.getElementById('mNotes').value.trim(),
      created_by: this.currentUser ? this.currentUser.id : 1,
      created_at: new Date().toISOString(),
      sync_status: this.isOnline ? 'SYNCED' : 'PENDING_SYNC'
    };

    // Calculate estimated EDD if LMP entered
    if (patientData.lmp_date) {
      const lmp = new Date(patientData.lmp_date);
      lmp.setDate(lmp.getDate() + 280); // Naegele's rule: +9 months 7 days (~280 days)
      patientData.edd_date = lmp.toISOString().split('T')[0];
    }

    if (this.isOnline) {
      try {
        const res = await this.apiFetch('/api/patients', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patientData)
        });
        if (!res.ok) throw new Error("Failed to save mother online");
        alert("Mother record registered and saved to SQL database.");
      } catch (err) {
        // Fallback to offline queue
        this.offlineQueue.patients.push(patientData);
        this.saveOfflineQueue();
        this.setSyncStatus(this.isOnline ? 'PENDING SYNC' : 'OFFLINE');
        alert("Server unreachable. Mother record stored securely in offline queue (Pending Sync).");
      }
    } else {
      this.offlineQueue.patients.push(patientData);
      this.saveOfflineQueue();
      this.setSyncStatus('OFFLINE');
      alert("Mother record saved offline (Pending Sync). Will synchronize automatically when connected.");
    }

    document.getElementById('addMotherForm').reset();
    this.showView('mothers');
  },

  openMaternalCheckFor(patientId, patientName, patientAge) {
    this.showView('maternal-predict');
    const select = document.getElementById('predPatientSelect');
    select.innerHTML = `<option value="${patientId}" selected>${patientName} (Age ${patientAge})</option>`;
    document.getElementById('predAge').value = patientAge;
  },

  // 8. Maternal Risk Prediction (ML Model)
  prepareMaternalPredictView() {
    // Populate registered mothers into select
    const select = document.getElementById('predPatientSelect');
    select.innerHTML = `<option value="">-- Quick Check (No record saved) --</option>`;
    const all = [...this.offlineQueue.patients, ...(this.cachedData.patients || [])];
    all.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id || p.client_uid;
      opt.textContent = `${p.full_name} (${p.village}, Age ${p.age})`;
      opt.dataset.age = p.age;
      select.appendChild(opt);
    });

    select.onchange = (e) => {
      const selected = select.options[select.selectedIndex];
      if (selected.dataset.age) {
        document.getElementById('predAge').value = selected.dataset.age;
      }
    };
  },

  populateSampleRisk(type) {
    if (type === 'high') {
      document.getElementById('predAge').value = 36;
      document.getElementById('predSystolicBP').value = 145;
      document.getElementById('predDiastolicBP').value = 95;
      document.getElementById('predBS').value = 14.0;
      document.getElementById('predBodyTemp').value = 98.6;
      document.getElementById('predHeartRate').value = 88;
    } else {
      document.getElementById('predAge').value = 23;
      document.getElementById('predSystolicBP').value = 90;
      document.getElementById('predDiastolicBP').value = 60;
      document.getElementById('predBS').value = 7.0;
      document.getElementById('predBodyTemp').value = 98.0;
      document.getElementById('predHeartRate').value = 76;
    }
  },

  async handleMaternalPredict(e) {
    e.preventDefault();
    const payload = {
      Age: parseFloat(document.getElementById('predAge').value),
      SystolicBP: parseFloat(document.getElementById('predSystolicBP').value),
      DiastolicBP: parseFloat(document.getElementById('predDiastolicBP').value),
      BS: parseFloat(document.getElementById('predBS').value),
      BodyTemp: parseFloat(document.getElementById('predBodyTemp').value),
      HeartRate: parseFloat(document.getElementById('predHeartRate').value)
    };

    const patientId = document.getElementById('predPatientSelect').value;
    const resultBox = document.getElementById('predictionResultCard');
    resultBox.style.display = 'block';
    resultBox.innerHTML = `<div class="card" style="text-align:center; padding:20px;">Analyzing clinical parameters with trained RandomForestClassifier model (POST /api/maternal/predict)...</div>`;

    try {
      // The local FastAPI server is the local inference engine.
      // Internet connectivity is NOT required to call localhost.
      const res = await this.apiFetch('/api/maternal/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned HTTP ${res.status}`);
      }

      const prediction = await res.json();
      this.renderPredictionResult(prediction, patientId, payload);
    } catch (err) {
      resultBox.innerHTML = `
        <div class="alert-box danger" style="padding:16px;">
          <h4 style="margin:0 0 6px 0; font-size:15px;">⚠️ Local ML Inference Backend Unavailable</h4>
          <p style="margin:0; font-size:13.5px;">
            Unable to connect to local FastAPI inference service (${err.message}). Ensure the local MediConnect backend is running (<code>python run_app.py</code>).
          </p>
          <p style="margin:8px 0 0 0; font-size:12px; color:var(--text-muted);">
            Note: MediConnect strictly uses the trained production model (<code>ml/maternal_risk_model.joblib</code>) and does not generate unverified heuristic predictions when the backend service is offline.
          </p>
        </div>
      `;
    }
  },

  renderPredictionResult(pred, patientId, inputs) {
    const isHi = window.i18n && window.i18n.currentLang === 'hi';
    const isHigh = pred.risk_level === "High Risk";
    const isMed = pred.risk_level === "Medium Risk";
    const badgeColor = isHigh ? 'var(--risk-high)' : (isMed ? 'var(--risk-med)' : 'var(--risk-low)');
    const cardBg = isHigh ? 'var(--risk-high-bg)' : (isMed ? 'var(--risk-med-bg)' : 'var(--risk-low-bg)');
    const cardBorder = isHigh ? 'var(--risk-high-border)' : (isMed ? 'var(--risk-med-border)' : 'var(--risk-low-border)');

    const displayRiskText = isHi
      ? (isHigh ? 'उच्च जोखिम (High Risk)' : (isMed ? 'मध्यम जोखिम (Medium Risk)' : 'कम जोखिम (Low Risk)'))
      : pred.risk_level;

    let referralAlert = '';
    if (pred.requires_referral) {
      referralAlert = `
        <div class="alert-box danger" style="margin-top:16px;">
          <h4 style="font-size:15px; margin-bottom:4px;">⚠️ ${isHi ? 'आशा कार्यकर्ता हेतु मार्गदर्शन:' : 'CLINICAL PROCEDURAL GUIDANCE:'}</h4>
          <p style="font-size:14px; font-weight:600; margin:0;">
            ${isHi ? 'उच्च जोखिम मामला पाया गया। स्थापित नैदानिक/रेफरल प्रक्रियाओं के अनुसार समीक्षा करें।' : 'High-risk case identified. Review according to established clinical/referral procedures.'}
          </p>
          <ul style="margin:8px 0 0 20px; font-size:13px;">
            <li>${isHi ? 'उप-केंद्र पर एएनएम / चिकित्सा अधिकारी से परामर्श लें' : 'Notify ANM / Medical Officer at Sub-Center per established protocol'}</li>
            <li>${isHi ? 'आवश्यकता पड़ने पर 102/108 परिवहन की व्यवस्था करें' : 'Follow referral transport procedures if danger signs arise'}</li>
            <li>${isHi ? 'परिवार को संस्थागत प्रसव के महत्व पर परामर्श दें' : 'Counsel family regarding institutional delivery procedures'}</li>
          </ul>
        </div>
      `;
    }

    const probVal = pred.predicted_class_probability !== undefined ? pred.predicted_class_probability : (pred.confidence || 0.0);
    const algoName = pred.algorithm || 'RandomForestClassifier';

    const resultBox = document.getElementById('predictionResultCard');
    resultBox.innerHTML = `
      <div class="card" style="background:${cardBg}; border:2px solid ${cardBorder};">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div>
            <div style="font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; color:${badgeColor};">
              ${isHi ? 'अनुमानित जोखिम स्तर' : 'Risk Level'}
            </div>
            <div style="font-size:32px; font-weight:900; color:${badgeColor}; margin-top:4px;">
              ${displayRiskText}
            </div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:13px; color:var(--text-muted);">${isHi ? 'अनुमानित प्रायिकता' : 'Predicted Class Probability'}</div>
            <div style="font-size:22px; font-weight:800;">${Math.round(probVal * 100)}%</div>
            <div style="font-size:11px; color:var(--text-muted);">${algoName} (${pred.model_version})</div>
          </div>
        </div>

        ${referralAlert}

        <div style="background:white; padding:14px; border-radius:var(--radius-sm); margin-top:16px; border:1px solid var(--border-subtle);">
          <div style="font-weight:700; font-size:13px; margin-bottom:6px;">${isHi ? 'जांचे गए स्वास्थ्य मापक:' : 'Features Used (6 Parameters):'}</div>
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:8px; font-size:13px;">
            <div>${isHi ? 'उम्र' : 'Age'}: <strong>${inputs.Age} ${isHi ? 'वर्ष' : 'yrs'}</strong></div>
            <div>BP: <strong>${inputs.SystolicBP}/${inputs.DiastolicBP} mmHg</strong></div>
            <div>${isHi ? 'शुगर' : 'BS (Blood Sugar)'}: <strong>${inputs.BS} mmol/L</strong></div>
            <div>${isHi ? 'तापमान' : 'BodyTemp'}: <strong>${inputs.BodyTemp} °F</strong></div>
            <div>${isHi ? 'नाड़ी दर' : 'HeartRate'}: <strong>${inputs.HeartRate} BPM</strong></div>
          </div>
        </div>

        <div style="font-size:12px; color:var(--text-muted); margin-top:12px; font-style:italic;">
          * ${isHi ? 'केवल निर्णय-समर्थन हेतु पूर्वानुमान। यह चिकित्सीय निदान नहीं है।' : (pred.disclaimer || 'Decision-support prediction only. This is not a medical diagnosis.')}
        </div>
        <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">
          * ${isHi ? 'उच्च-जोखिम मामलों का शीघ्र पता लगाने हेतु हाई-रिस्क रिकॉल को प्राथमिक मूल्यांकन मीट्रिक माना गया है।' : 'High-Risk Recall is used as the primary evaluation metric to prioritize detection of high-risk cases.'}
        </div>

        ${patientId ? `
          <div style="margin-top:16px;">
            <button class="btn btn-primary" onclick="app.saveMaternalVisitRecord('${patientId}', '${pred.risk_level}', ${probVal})">
              ${isHi ? 'महिला के स्वास्थ्य रिकॉर्ड में सहेजें' : "Save Clinical Visit to Mother's Health Record"}
            </button>
          </div>
        ` : ''}
      </div>
    `;
  },

  async saveMaternalVisitRecord(patientId, riskLevel, confidence) {
    const payload = {
      client_uid: `MR-LOCAL-${Date.now()}`,
      patient_id: isNaN(patientId) ? 1 : parseInt(patientId),
      patient_client_uid: isNaN(patientId) ? patientId : null,
      visit_number: 1,
      Age: parseFloat(document.getElementById('predAge').value),
      SystolicBP: parseFloat(document.getElementById('predSystolicBP').value),
      DiastolicBP: parseFloat(document.getElementById('predDiastolicBP').value),
      BS: parseFloat(document.getElementById('predBS').value),
      BodyTemp: parseFloat(document.getElementById('predBodyTemp').value),
      HeartRate: parseFloat(document.getElementById('predHeartRate').value),
      risk_level: riskLevel,
      confidence: confidence,
      notes: "Field ANC checkup with ML decision support",
      recorded_by: this.currentUser ? this.currentUser.id : 1,
      recorded_at: new Date().toISOString(),
      sync_status: this.isOnline ? 'SYNCED' : 'PENDING_SYNC'
    };

    if (this.isOnline && !isNaN(patientId)) {
      try {
        await this.apiFetch('/api/maternal/records', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        alert("Visit saved to SQL database.");
      } catch (e) {
        this.offlineQueue.maternal_records.push(payload);
        this.saveOfflineQueue();
        this.setSyncStatus(this.isOnline ? 'PENDING SYNC' : 'OFFLINE');
        alert("Server unreachable. Saved visit record to offline queue (Pending Sync).");
      }
    } else {
      this.offlineQueue.maternal_records.push(payload);
      this.saveOfflineQueue();
      this.setSyncStatus('OFFLINE');
      alert("Saved visit record to offline queue (Pending Sync). Will synchronize automatically when connected.");
    }
    this.showView('mothers');
  },

  // 9. Children & Immunization
  async loadChildren() {
    try {
      let children = [];
      if (this.isOnline) {
        try {
          const res = await this.apiFetch('/api/children');
          if (res.ok) {
            const data = await res.json();
            children = data.children || [];
            this.cachedData.children = children;
          } else {
            children = this.cachedData.children || [];
          }
        } catch (fetchErr) {
          children = this.cachedData.children || [];
        }
      } else {
        children = this.cachedData.children || [];
      }

      const merged = [...this.offlineQueue.children, ...children];
      const tbody = document.getElementById('childrenTableBody');
      tbody.innerHTML = '';

      if (merged.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No child records registered yet.</td></tr>`;
        return;
      }

      merged.forEach(c => {
        const dob = new Date(c.dob);
        const ageMonths = Math.round((Date.now() - dob.getTime()) / (1000 * 60 * 60 * 24 * 30.4) * 10) / 10;
        const tr = document.createElement('tr');

        const overdueCount = c.overdue_vaccines || 0;
        const statusBadge = overdueCount > 0
          ? `<span class="badge badge-overdue">${overdueCount} Overdue</span>`
          : `<span class="badge badge-completed">Up to date (${c.completed_vaccines || 0} given)</span>`;

        const isPending = (c.sync_status === 'PENDING_SYNC') || (this.offlineQueue.children || []).some(x => x.client_uid === c.client_uid);
        const syncBadge = isPending ? `<span class="badge badge-due">Pending Sync</span>` : '';

        tr.innerHTML = `
          <td><code>${c.rch_child_id || c.client_uid || 'CH-' + c.id}</code></td>
          <td><strong>${c.name}</strong></td>
          <td>${c.mother_name || c.guardian_name || 'Guardian'}</td>
          <td>${c.gender}</td>
          <td>${c.dob}</td>
          <td>${ageMonths} months</td>
          <td>${c.village}</td>
          <td>${statusBadge} ${syncBadge}</td>
          <td>
            <button type="button" class="btn btn-outline btn-sm btn-view-schedule" data-id="${c.id || 0}" data-uid="${c.client_uid || ''}" data-name="${(c.name || '').replace(/"/g, '&quot;')}" data-dob="${c.dob}" data-gender="${c.gender}" data-village="${c.village}" onclick="app.showChildImmunizationDetails(this, ${c.id || 0}, '${c.client_uid || ''}')">
              📅 View Schedule
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error(e);
    }
  },

  populateMotherSelectForChild() {
    const select = document.getElementById('chMotherId');
    select.innerHTML = `<option value="">-- No linked mother registered --</option>`;
    const all = [...this.offlineQueue.patients, ...(this.cachedData.patients || [])];
    all.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id || p.client_uid;
      opt.textContent = `${p.full_name} (${p.village})`;
      select.appendChild(opt);
    });
  },

  // UIP Vaccination Template & Milestones
  uipScheduleTemplate: [
    { vaccine_name: "BCG", dose_number: 1, days: 0, milestone: "At Birth" },
    { vaccine_name: "Hep B (Birth)", dose_number: 1, days: 0, milestone: "At Birth" },
    { vaccine_name: "OPV (Birth)", dose_number: 0, days: 0, milestone: "At Birth" },
    { vaccine_name: "Pentavalent", dose_number: 1, days: 42, milestone: "6 Weeks" },
    { vaccine_name: "OPV", dose_number: 1, days: 42, milestone: "6 Weeks" },
    { vaccine_name: "Pentavalent", dose_number: 2, days: 70, milestone: "10 Weeks" },
    { vaccine_name: "OPV", dose_number: 2, days: 70, milestone: "10 Weeks" },
    { vaccine_name: "Pentavalent", dose_number: 3, days: 98, milestone: "14 Weeks" },
    { vaccine_name: "OPV", dose_number: 3, days: 98, milestone: "14 Weeks" },
    { vaccine_name: "Measles-Rubella (MR)", dose_number: 1, days: 274, milestone: "9–12 Months" },
    { vaccine_name: "Vitamin A", dose_number: 1, days: 274, milestone: "9–12 Months" },
    { vaccine_name: "DPT Booster", dose_number: 1, days: 485, milestone: "16–24 Months" }
  ],
  currentScheduleData: null,

  getVaccineMilestone(vname, dose) {
    if (!vname) return "Routine";
    if (vname.includes("Birth") || vname === "BCG") return "At Birth";
    if (dose === 1 && (vname.includes("Pentavalent") || vname.includes("OPV"))) return "6 Weeks";
    if (dose === 2 && (vname.includes("Pentavalent") || vname.includes("OPV"))) return "10 Weeks";
    if (dose === 3 && (vname.includes("Pentavalent") || vname.includes("OPV"))) return "14 Weeks";
    if (vname.includes("Measles") || vname.includes("Vitamin A")) return "9–12 Months";
    if (vname.includes("Booster") || vname.includes("DPT")) return "16–24 Months";
    return "Routine";
  },

  previewUIPScheduleFromForm() {
    const dobVal = document.getElementById('chDob').value;
    if (!dobVal) {
      alert("Please enter the Child's Date of Birth first to calculate and preview the UIP schedule.");
      document.getElementById('chDob').focus();
      return;
    }
    const nameVal = document.getElementById('chName').value.trim() || 'New Child (Registration Preview)';
    const villageVal = document.getElementById('chVillage').value || 'Field Village';
    const genderVal = document.getElementById('chGender').value || 'Female';
    const motherSelect = document.getElementById('chMotherId');
    const motherText = motherSelect.selectedIndex > 0 ? motherSelect.options[motherSelect.selectedIndex].text : 'Unlinked';

    const dob = new Date(dobVal);
    const now = new Date();
    const ageMonths = Math.max(0, Math.round((now.getTime() - dob.getTime()) / (1000 * 60 * 60 * 24 * 30.4) * 10) / 10);

    const generatedImms = this.uipScheduleTemplate.map((item, idx) => {
      const dueDate = new Date(dob.getTime() + item.days * 24 * 60 * 60 * 1000);
      const dueStr = dueDate.toISOString().split('T')[0];
      let status = 'SCHEDULED';
      const overdueThreshold = new Date(dueDate.getTime() + 28 * 24 * 60 * 60 * 1000);
      if (now > overdueThreshold) {
        status = 'FOLLOW_UP_REQUIRED';
      } else if (now >= dueDate) {
        status = 'DUE';
      }
      return {
        id: `PREVIEW-${idx}`,
        vaccine_name: item.vaccine_name,
        dose_number: item.dose_number,
        due_date: dueStr,
        status: status,
        given_date: null,
        batch_no: '',
        notes: '',
        milestone: item.milestone,
        isPreview: true
      };
    });

    const mockChild = {
      id: 0,
      name: nameVal,
      gender: genderVal,
      dob: dobVal,
      age_months: ageMonths,
      village: villageVal,
      mother_name: motherText,
      rch_child_id: 'PREVIEW-GENERATED',
      isPreview: true
    };

    this.displayScheduleModal(mockChild, generatedImms, true);
  },

  async showChildImmunizationDetails(childId, clientUid) {
    try {
      // Normalize arguments (handles string client_uid passed as first argument)
      if (typeof childId === 'string' && (childId.startsWith('CH-') || isNaN(parseInt(childId)))) {
        if (!clientUid) clientUid = childId;
        childId = 0;
      }
      childId = parseInt(childId) || 0;

      let child = null;
      let immunizations = [];

      // Try server if online and childId > 0
      if (this.isOnline && childId > 0) {
        try {
          const res = await this.apiFetch(`/api/children/${childId}`);
          if (res.ok) {
            const data = await res.json();
            child = data.child;
            immunizations = data.immunizations || [];
          }
        } catch (fetchErr) {
          console.warn("Could not fetch child details from server, falling back to local cache", fetchErr);
        }
      }

      // Check offlineQueue or cachedData
      if (!child) {
        const localList = [...this.offlineQueue.children, ...(this.cachedData.children || [])];
        child = localList.find(c => 
          (childId > 0 && c.id == childId) || 
          (clientUid && c.client_uid == clientUid) ||
          (clientUid && c.name && c.name.toLowerCase() === String(clientUid).toLowerCase())
        );
      }

      // Fallback: Read child details directly from visible DOM table rows
      if (!child) {
        const rows = document.querySelectorAll('#childrenTableBody tr');
        for (const row of rows) {
          const text = row.textContent;
          if ((clientUid && text.includes(clientUid)) || (childId > 0 && text.includes(String(childId)))) {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 7) {
              child = {
                id: childId,
                client_uid: cells[0].textContent.trim(),
                name: cells[1].textContent.trim(),
                guardian_name: cells[2].textContent.trim(),
                gender: cells[3].textContent.trim() || 'Male',
                dob: cells[4].textContent.trim() || new Date().toISOString().split('T')[0],
                village: cells[6].textContent.trim() || 'Field Village'
              };
              break;
            }
          }
        }
      }

      // If still not found but there are rows in the table, pick matching row or first row
      if (!child) {
        const firstRow = document.querySelector('#childrenTableBody tr');
        if (firstRow && firstRow.querySelectorAll('td').length >= 7) {
          const cells = firstRow.querySelectorAll('td');
          child = {
            id: childId,
            client_uid: cells[0].textContent.trim(),
            name: cells[1].textContent.trim(),
            guardian_name: cells[2].textContent.trim(),
            gender: cells[3].textContent.trim() || 'Male',
            dob: cells[4].textContent.trim() || new Date().toISOString().split('T')[0],
            village: cells[6].textContent.trim() || 'Field Village'
          };
        }
      }

      if (!child) {
        alert("Child record could not be loaded. Please ensure child is saved.");
        return;
      }

      // Generate local schedule if missing
      if (!immunizations || immunizations.length === 0) {
        const dob = new Date(child.dob);
        const now = new Date();
        immunizations = this.uipScheduleTemplate.map((item, idx) => {
          const dueDate = new Date(dob.getTime() + item.days * 24 * 60 * 60 * 1000);
          const dueStr = dueDate.toISOString().split('T')[0];
          let status = 'SCHEDULED';
          const overdueThreshold = new Date(dueDate.getTime() + 28 * 24 * 60 * 60 * 1000);
          if (now > overdueThreshold) {
            status = 'FOLLOW_UP_REQUIRED';
          } else if (now >= dueDate) {
            status = 'DUE';
          }
          return {
            id: `LOCAL-${child.id || 0}-${idx}`,
            child_id: child.id,
            vaccine_name: item.vaccine_name,
            dose_number: item.dose_number,
            due_date: dueStr,
            status: status,
            given_date: null,
            batch_no: '',
            notes: '',
            milestone: item.milestone
          };
        });
      } else {
        immunizations.forEach(i => {
          if (!i.milestone) {
            i.milestone = this.getVaccineMilestone(i.vaccine_name, i.dose_number);
          }
        });
      }

      this.displayScheduleModal(child, immunizations, false);
    } catch (err) {
      console.error("Error opening child schedule:", err);
      alert("Failed to load immunization schedule: " + err.message);
    }
  },

  ensureScheduleModalInDom() {
    let modal = document.getElementById('childScheduleModal');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = 'childScheduleModal';
    modal.className = 'modal-overlay';
    modal.style.display = 'none';
    modal.onclick = (e) => { if (e.target === modal) app.closeScheduleModal(); };
    modal.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-header">
          <div>
            <h3 id="scheduleModalTitle" style="margin-bottom:2px; font-size:18px;">👶 Child Immunization Schedule (UIP)</h3>
            <p id="scheduleModalSubtitle" style="font-size:13px; color:var(--text-muted); margin:0;">Universal Immunization Programme schedule & tracking</p>
          </div>
          <button class="modal-close" onclick="app.closeScheduleModal()">&times;</button>
        </div>
        <div class="modal-body" style="padding:18px;">
          <div id="scheduleChildBanner" style="background:var(--primary-light, #E8F5F4); border:1px solid var(--border-strong, #A8BCB7); border-radius:10px; padding:12px 16px; margin-bottom:16px; display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; font-size:13px;">
          </div>
          <div style="margin-bottom:16px; background:#fff; border:1px solid var(--border-subtle, #D5DFDC); border-radius:10px; padding:14px 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:13px; font-weight:700;">
              <span>UIP Vaccination Progress</span>
              <span id="scheduleProgressText">0 / 12 Vaccines Completed (0%)</span>
            </div>
            <div style="height:10px; background:#F6F8F8; border-radius:5px; overflow:hidden; border:1px solid #D5DFDC;">
              <div id="scheduleProgressBar" style="height:100%; width:0%; background:var(--primary, #0D7A73); transition:width 0.3s ease;"></div>
            </div>
            <div id="scheduleStatBadges" style="display:flex; gap:10px; margin-top:10px; flex-wrap:wrap; font-size:12px;"></div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; gap:6px;">
              <button type="button" class="btn btn-outline btn-sm active" id="btnFilterAll" onclick="app.filterSchedule('ALL')">All Doses (12)</button>
              <button type="button" class="btn btn-outline btn-sm" id="btnFilterPending" onclick="app.filterSchedule('PENDING')">Due / Overdue</button>
              <button type="button" class="btn btn-outline btn-sm" id="btnFilterCompleted" onclick="app.filterSchedule('COMPLETED')">Completed</button>
            </div>
            <span style="font-size:12px; color:var(--text-muted, #53635E);">Standard UIP India Schedule (Birth to 24 Months)</span>
          </div>
          <div class="table-responsive" style="max-height:380px; overflow-y:auto; border:1px solid #D5DFDC; border-radius:6px;">
            <table class="data-table" style="margin:0; width:100%;">
              <thead style="position:sticky; top:0; background:#f0f4f3; z-index:1;">
                <tr>
                  <th>Age Milestone</th>
                  <th>Vaccine Name</th>
                  <th>Dose</th>
                  <th>Due Date</th>
                  <th>Status</th>
                  <th>Administered Info</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody id="scheduleTableBody"></tbody>
            </table>
          </div>
          <div style="margin-top:16px; display:flex; justify-content:flex-end;">
            <button type="button" class="btn btn-outline" onclick="app.closeScheduleModal()">Close Schedule</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  },

  displayScheduleModal(child, immunizations, isPreview = false) {
    const modalEl = this.ensureScheduleModalInDom();
    const dob = new Date(child.dob);
    const now = new Date();
    const ageMonths = Math.max(0, Math.round((now.getTime() - dob.getTime()) / (1000 * 60 * 60 * 24 * 30.4) * 10) / 10);

    const banner = document.getElementById('scheduleChildBanner');
    banner.innerHTML = `
      <div><strong>Child:</strong> ${child.name} (${child.gender})</div>
      <div><strong>DOB:</strong> ${child.dob} (${ageMonths} months)</div>
      <div><strong>Village:</strong> ${child.village || 'N/A'}</div>
      <div><strong>Mother / Guardian:</strong> ${child.mother_name || child.guardian_name || 'N/A'}</div>
      <div><strong>RCH ID:</strong> <code>${child.rch_child_id || child.client_uid || 'CH-' + (child.id || 0)}</code></div>
      <div><strong>Mode:</strong> ${isPreview ? '<span class="badge badge-due">Preview Mode</span>' : '<span class="badge badge-completed">Active Record</span>'}</div>
    `;

    document.getElementById('scheduleModalTitle').textContent = isPreview
      ? `📅 UIP Schedule Preview: ${child.name}`
      : `👶 Immunization Schedule: ${child.name}`;
    document.getElementById('scheduleModalSubtitle').textContent = isPreview
      ? `Calculated based on Date of Birth (${child.dob}) for preview before registration`
      : `Complete Universal Immunization Programme (UIP) timeline & dose tracking`;

    const total = immunizations.length;
    const completed = immunizations.filter(i => i.status === 'COMPLETED').length;
    const due = immunizations.filter(i => i.status === 'DUE').length;
    const overdue = immunizations.filter(i => i.status === 'OVERDUE' || i.status === 'FOLLOW_UP_REQUIRED').length;
    const scheduled = immunizations.filter(i => i.status === 'SCHEDULED').length;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

    document.getElementById('scheduleProgressText').textContent = `${completed} / ${total} Vaccines Completed (${pct}%)`;
    document.getElementById('scheduleProgressBar').style.width = `${pct}%`;

    const badgesContainer = document.getElementById('scheduleStatBadges');
    badgesContainer.innerHTML = `
      <span class="badge badge-completed">✓ ${completed} Completed</span>
      <span class="badge badge-due">⏳ ${due} Due Now</span>
      <span class="badge badge-overdue">⚠️ ${overdue} Overdue</span>
      <span class="badge badge-scheduled">📅 ${scheduled} Scheduled</span>
    `;

    this.currentScheduleData = { child, immunizations, isPreview };

    document.querySelectorAll('#btnFilterAll, #btnFilterPending, #btnFilterCompleted').forEach(b => b.classList.remove('active'));
    document.getElementById('btnFilterAll').classList.add('active');

    this.renderScheduleTable('ALL');
    document.getElementById('childScheduleModal').style.display = 'flex';
  },

  filterSchedule(filterType) {
    document.querySelectorAll('#btnFilterAll, #btnFilterPending, #btnFilterCompleted').forEach(b => b.classList.remove('active'));
    if (filterType === 'ALL') document.getElementById('btnFilterAll').classList.add('active');
    if (filterType === 'PENDING') document.getElementById('btnFilterPending').classList.add('active');
    if (filterType === 'COMPLETED') document.getElementById('btnFilterCompleted').classList.add('active');
    this.renderScheduleTable(filterType);
  },

  renderScheduleTable(filterType) {
    if (!this.currentScheduleData) return;
    const { child, immunizations, isPreview } = this.currentScheduleData;
    const tbody = document.getElementById('scheduleTableBody');
    tbody.innerHTML = '';

    let items = immunizations;
    if (filterType === 'PENDING') {
      items = immunizations.filter(i => i.status !== 'COMPLETED');
    } else if (filterType === 'COMPLETED') {
      items = immunizations.filter(i => i.status === 'COMPLETED');
    }

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No vaccine records match the selected filter.</td></tr>`;
      return;
    }

    items.forEach(item => {
      const tr = document.createElement('tr');
      let statusBadge = '';
      if (item.status === 'COMPLETED') {
        statusBadge = `<span class="badge badge-completed">✓ Completed</span>`;
      } else if (item.status === 'DUE') {
        statusBadge = `<span class="badge badge-due">⏳ Due Now</span>`;
      } else if (item.status === 'OVERDUE' || item.status === 'FOLLOW_UP_REQUIRED') {
        statusBadge = `<span class="badge badge-overdue">⚠️ Overdue / Follow-Up</span>`;
      } else {
        statusBadge = `<span class="badge badge-scheduled">📅 Scheduled</span>`;
      }

      let adminInfo = '-';
      if (item.status === 'COMPLETED') {
        adminInfo = `<div><strong>Date:</strong> ${item.given_date || 'Recorded'}</div>`;
        if (item.batch_no) adminInfo += `<div style="font-size:11px; color:var(--text-muted);">Batch: ${item.batch_no}</div>`;
      }

      let actionCell = '';
      if (isPreview) {
        actionCell = `<span style="font-size:12px; color:var(--text-muted);">Will be generated upon submit</span>`;
      } else if (item.status === 'COMPLETED') {
        actionCell = `<span style="color:var(--risk-low); font-weight:700; font-size:13px;">✓ Given</span>`;
      } else {
        const safeChildName = (child.name || '').replace(/'/g, "\\'");
        const safeVaxName = (item.vaccine_name || '').replace(/'/g, "\\'");
        actionCell = `<button type="button" class="btn btn-primary btn-sm" onclick="app.openVaccineModalFromSchedule(${item.id || 0}, '${safeChildName}', '${safeVaxName}')">💉 Record Dose</button>`;
      }

      tr.innerHTML = `
        <td><span class="badge" style="background:#f0f4f3; color:var(--text-main);">${item.milestone || this.getVaccineMilestone(item.vaccine_name, item.dose_number)}</span></td>
        <td><strong>${item.vaccine_name}</strong></td>
        <td>Dose ${item.dose_number}</td>
        <td>${item.due_date}</td>
        <td>${statusBadge}</td>
        <td>${adminInfo}</td>
        <td>${actionCell}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  closeScheduleModal() {
    document.getElementById('childScheduleModal').style.display = 'none';
  },

  openVaccineModalFromSchedule(immId, childName, vaccineName) {
    this.openVaccineModal(immId, childName, vaccineName);
  },

  async handleAddChild(e) {
    e.preventDefault();
    const childData = {
      client_uid: `CH-LOCAL-${Date.now()}`,
      mother_id: document.getElementById('chMotherId').value ? parseInt(document.getElementById('chMotherId').value) : null,
      name: document.getElementById('chName').value.trim(),
      gender: document.getElementById('chGender').value,
      dob: document.getElementById('chDob').value,
      birth_weight: parseFloat(document.getElementById('chWeight').value) || null,
      village: (this.currentUser && this.currentUser.role === 'asha_worker') ? this.currentUser.village : document.getElementById('chVillage').value,
      created_by: this.currentUser ? this.currentUser.id : 1,
      created_at: new Date().toISOString(),
      sync_status: this.isOnline ? 'SYNCED' : 'PENDING_SYNC'
    };

    let newChildId = null;

    if (this.isOnline) {
      try {
        const res = await this.apiFetch('/api/children', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(childData)
        });
        if (!res.ok) throw new Error("Failed to register child");
        const resData = await res.json();
        newChildId = resData.id;
        alert("✓ Child registered successfully! Generated UIP immunization schedule.");
      } catch (err) {
        this.offlineQueue.children.push(childData);
        this.saveOfflineQueue();
        this.setSyncStatus(this.isOnline ? 'PENDING SYNC' : 'OFFLINE');
        alert("Server unreachable. Child record stored in offline queue (Pending Sync).");
      }
    } else {
      this.offlineQueue.children.push(childData);
      this.saveOfflineQueue();
      this.setSyncStatus('OFFLINE');
      alert("Child registered in offline queue (Pending Sync). Schedule will synchronize upon connection.");
    }

    document.getElementById('addChildForm').reset();
    this.showView('children');
    await this.loadChildren();

    // Automatically open the generated immunization schedule!
    if (newChildId) {
      this.showChildImmunizationDetails(newChildId, childData.client_uid);
    } else {
      this.showChildImmunizationDetails(0, childData.client_uid);
    }
  },

  // 10. Immunization Follow-Up
  async loadImmunizationFollowUp() {
    try {
      let list = [];
      if (this.isOnline) {
        try {
          const res = await this.apiFetch('/api/immunizations/follow-up');
          if (res.ok) {
            const data = await res.json();
            list = data.follow_up_list || [];
            this.cachedData.followups = list;
            const badge = document.getElementById('navOverdueBadge');
            if (badge) badge.textContent = data.summary?.overdue_count || 0;
          } else {
            list = this.cachedData.followups || [];
          }
        } catch (fetchErr) {
          list = this.cachedData.followups || [];
        }
      } else {
        list = this.cachedData.followups || [];
      }

      const tbody = document.getElementById('followupTableBody');
      tbody.innerHTML = '';

      if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="empty-state">${
          this.isOnline 
            ? 'No pending vaccinations due in this village! All children up to date.'
            : 'No cached follow-ups available while offline. You can view schedules and record vaccinations under Children.'
        }</td></tr>`;
        return;
      }

      list.forEach(item => {
        const tr = document.createElement('tr');
        const badgeClass = item.urgency === 'HIGH' ? 'badge-overdue' : (item.urgency === 'MEDIUM' ? 'badge-overdue' : 'badge-due');

        tr.innerHTML = `
          <td><span class="badge ${badgeClass}">${item.urgency_badge}</span></td>
          <td><strong>${item.child_name}</strong></td>
          <td>${item.mother_name}</td>
          <td>${item.child_age_months}m</td>
          <td>${item.village}</td>
          <td>${item.phone}</td>
          <td><strong>${item.vaccine_name}</strong> (Dose ${item.dose_number})</td>
          <td>${item.due_date}</td>
          <td style="font-size:12px; color:var(--text-muted);">${item.action_recommended}</td>
          <td>
            <button class="btn btn-primary btn-sm" onclick="app.openVaccineModal(${item.immunization_id}, '${(item.child_name || '').replace(/'/g, "\\'")}', '${item.vaccine_name}')">
              Record Dose
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error(e);
    }
  },

  openVaccineModal(immId, childName, vaccineName) {
    document.getElementById('modalImmId').value = immId;
    document.getElementById('modalChildDetails').textContent = `${childName} — ${vaccineName}`;
    document.getElementById('modalGivenDate').value = new Date().toISOString().split('T')[0];
    document.getElementById('vaccineModal').style.display = 'flex';
  },

  closeModal() {
    document.getElementById('vaccineModal').style.display = 'none';
  },

  async handleRecordVaccine(e) {
    e.preventDefault();
    const immId = document.getElementById('modalImmId').value;
    const givenDate = document.getElementById('modalGivenDate').value;
    const batchNo = document.getElementById('modalBatchNo').value.trim();
    const notes = document.getElementById('modalNotes').value.trim();

    const payload = {
      given_date: givenDate,
      batch_no: batchNo,
      notes: notes,
      status: 'COMPLETED',
      administered_by: this.currentUser ? this.currentUser.id : 1
    };

    if (this.isOnline) {
      try {
        const res = await this.apiFetch(`/api/immunizations/${immId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error("Failed to record vaccination");
        alert("Vaccine administered status updated in SQL database.");
      } catch (err) {
        this.offlineQueue.immunizations.push({ ...payload, immunization_id: immId, client_uid: `IMM-LOCAL-${immId}` });
        this.saveOfflineQueue();
        this.setSyncStatus(this.isOnline ? 'PENDING SYNC' : 'OFFLINE');
        alert("Server unreachable. Offline queue updated (Pending Sync). Will synchronize with server.");
      }
    } else {
      this.offlineQueue.immunizations.push({ ...payload, immunization_id: immId, client_uid: `IMM-LOCAL-${immId}` });
      this.saveOfflineQueue();
      this.setSyncStatus('OFFLINE');
      alert("Recorded in offline storage (Pending Sync). Status will sync when online.");
    }

    this.closeModal();
    this.loadImmunizationFollowUp();
    this.loadChildren();
    this.loadDashboardData();

    // If child schedule modal is currently open, refresh the schedule view
    if (this.currentScheduleData && this.currentScheduleData.child && document.getElementById('childScheduleModal').style.display !== 'none') {
      this.showChildImmunizationDetails(this.currentScheduleData.child.id, this.currentScheduleData.child.client_uid);
    }
  },

  async confirmCleanAllRecords() {
    const confirmed = confirm(
      "Are you sure you want to clean all records (patients, visits, children, immunizations, symptoms)?\n\n" +
      "This will reset the application to a completely fresh state. Staff user accounts (ASHA workers and supervisors) will be preserved."
    );
    if (!confirmed) return;

    try {
      if (this.isOnline) {
        const res = await this.apiFetch('/api/admin/clean-records', { method: 'POST' });
        if (!res.ok) throw new Error("Failed to clean database on server.");
      }
      
      this.offlineQueue = {
        patients: [],
        maternal_records: [],
        children: [],
        immunizations: [],
        symptoms: []
      };
      this.saveOfflineQueue();
      
      this.cachedData = {
        patients: [],
        children: [],
        followups: [],
        alerts: [],
        stats: null
      };
      localStorage.removeItem('mc_cached_stats');
      localStorage.removeItem('mc_last_sync_time');

      await this.loadDashboardData();
      await this.loadPatients();
      await this.loadChildren();
      await this.loadImmunizationFollowUp();
      await this.loadSymptoms();
      this.updateOfflineBadge();
      
      alert("✓ All records cleaned successfully! MediConnect is now completely fresh and ready for new entries.");
      this.showView('dashboard');
    } catch (err) {
      console.error(err);
      alert("Error cleaning records: " + err.message);
    }
  },

  // 11. Symptom Logging & Outbreak Alerts
  async handleAddSymptom(e) {
    e.preventDefault();
    const symData = {
      client_uid: `SYM-LOCAL-${Date.now()}`,
      village: (this.currentUser && this.currentUser.role === 'asha_worker') ? this.currentUser.village : document.getElementById('symVillage').value,
      person_name: document.getElementById('symPersonName').value.trim(),
      age: parseInt(document.getElementById('symAge').value) || null,
      gender: document.getElementById('symGender').value,
      symptom_type: document.getElementById('symType').value,
      severity: document.getElementById('symSeverity').value,
      onset_date: document.getElementById('symOnsetDate').value,
      notes: document.getElementById('symNotes').value.trim(),
      asha_id: this.currentUser ? this.currentUser.id : 1,
      recorded_at: new Date().toISOString()
    };

    if (this.isOnline) {
      try {
        const res = await this.apiFetch('/api/symptoms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(symData)
        });
        const result = await res.json();
        alert(result.outbreak_alert_status ? "Symptom case logged. NOTE: Outbreak alert threshold triggered for this village!" : "Symptom case logged successfully.");
      } catch (err) {
        this.offlineQueue.symptoms.push(symData);
        this.saveOfflineQueue();
        this.setSyncStatus(this.isOnline ? 'PENDING SYNC' : 'OFFLINE');
        alert("Server unreachable. Saved symptom case locally in offline queue (Pending Sync).");
      }
    } else {
      this.offlineQueue.symptoms.push(symData);
      this.saveOfflineQueue();
      this.setSyncStatus('OFFLINE');
      alert("Symptom case saved offline (Pending Sync). Will synchronize automatically when connected.");
    }

    document.getElementById('symptomForm').reset();
    this.showView('outbreak-alerts');
  },

  async loadOutbreakAlerts() {
    try {
      let data = null;
      if (this.isOnline) {
        try {
          const res = await this.apiFetch('/api/outbreak/alerts');
          if (res.ok) {
            data = await res.json();
            this.cachedData.alerts = data;
          }
        } catch (fetchErr) {
          data = this.cachedData.alerts || null;
        }
      } else {
        data = this.cachedData.alerts || null;
      }

      const alertContainer = document.getElementById('outbreakAlertsContainer');
      const vTable = document.getElementById('outbreakVillagesTableBody');
      const lTable = document.getElementById('recentSymptomsTableBody');
      const navBadge = document.getElementById('navAlertBadge');

      if (data) {
        if (navBadge) navBadge.textContent = data.active_alerts_count;
        alertContainer.innerHTML = '';

        if (data.alerts.length === 0) {
          alertContainer.innerHTML = `
            <div class="alert-box success">
              <h4>No Active Outbreak Clusters Detected</h4>
              <p>Village symptom levels are currently within historical baseline expectations. Continuous surveillance is active.</p>
            </div>
          `;
        } else {
          data.alerts.forEach(alertItem => {
            alertContainer.innerHTML += `
              <div class="alert-box danger">
                <h4>🚨 ${alertItem.badge}: Village ${alertItem.village}</h4>
                <p style="font-size:14px; font-weight:600; margin-top:4px;">${alertItem.message}</p>
                <div style="background:white; padding:10px; border-radius:4px; margin-top:10px; font-size:13px; color:var(--text-main);">
                  <strong>Advisory / Field Action for ASHA:</strong> ${alertItem.action_recommendation}
                </div>
              </div>
            `;
          });
        }

        // Monitored villages table
        vTable.innerHTML = '';
        for (const [vName, rows] of Object.entries(data.monitored_villages || {})) {
          rows.forEach(r => {
            const badgeClass = r.is_anomaly ? 'badge-high-risk' : (r.status === 'INSUFFICIENT_DATA' ? 'badge-offline' : 'badge-completed');
            vTable.innerHTML += `
              <tr>
                <td><strong>${r.village}</strong></td>
                <td>${r.symptom_type}</td>
                <td><strong>${r.recent_cases_7d}</strong></td>
                <td>${r.severe_cases}</td>
                <td>${r.historical_baseline_7d}</td>
                <td><span class="badge ${badgeClass}">${r.badge}</span></td>
                <td style="font-size:12px;">${r.action_recommendation}</td>
              </tr>
            `;
          });
        }
      } else {
        if (navBadge) navBadge.textContent = '0';
        alertContainer.innerHTML = `
          <div class="alert-box warning">
            <h4>⚠️ Outbreak Statistical Surveillance Offline</h4>
            <p>Historical baseline anomaly calculations require an active server connection. You can still log new symptom cases below while offline — they are safely queued in local storage and will sync automatically when connected.</p>
          </div>
        `;
        vTable.innerHTML = `<tr><td colspan="7" class="empty-state">Statistical baseline data requires an active server connection.</td></tr>`;
      }

      // Recent logs table — ALWAYS include pending offline symptoms!
      lTable.innerHTML = '';

      // Prepend pending offline symptom entries
      (this.offlineQueue.symptoms || []).forEach(log => {
        lTable.innerHTML += `
          <tr style="background:#FFFBEB;">
            <td>${log.onset_date}</td>
            <td>${log.village}</td>
            <td><strong>${log.person_name}</strong></td>
            <td>${log.age || '-'} / ${log.gender}</td>
            <td>${log.symptom_type}</td>
            <td><span class="badge badge-due">Pending Sync</span></td>
          </tr>
        `;
      });

      if (data && data.recent_logs) {
        data.recent_logs.forEach(log => {
          lTable.innerHTML += `
            <tr>
              <td>${log.onset_date}</td>
              <td>${log.village}</td>
              <td><strong>${log.person_name}</strong></td>
              <td>${log.age || '-'} / ${log.gender}</td>
              <td>${log.symptom_type}</td>
              <td><span class="badge ${log.severity === 'Severe' ? 'badge-high-risk' : 'badge-completed'}">${log.severity}</span></td>
            </tr>
          `;
        });
      } else if ((this.offlineQueue.symptoms || []).length === 0) {
        lTable.innerHTML = `<tr><td colspan="6" class="empty-state">No recent symptom logs recorded.</td></tr>`;
      }
    } catch (e) {
      console.error(e);
    }
  },

  // 12. Model Status & Admin Retraining
  async loadModelStatus() {
    try {
      const res = await this.apiFetch('/api/model/status');
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      if (document.getElementById('modAlgorithm')) document.getElementById('modAlgorithm').textContent = data.algorithm;
      if (document.getElementById('modVersion')) document.getElementById('modVersion').textContent = `Version ${data.model_version} (${data.dataset_name})`;
      if (document.getElementById('modHighRecall')) document.getElementById('modHighRecall').textContent = `${Math.round(data.evaluation_metrics.per_class['High Risk'].recall * 1000) / 10}%`;
      if (document.getElementById('modMacroRecall')) document.getElementById('modMacroRecall').textContent = `${Math.round(data.evaluation_metrics.recall_macro * 1000) / 10}%`;
      if (document.getElementById('modMacroPrecision')) document.getElementById('modMacroPrecision').textContent = `${Math.round(data.evaluation_metrics.precision_macro * 1000) / 10}%`;
      if (document.getElementById('modMacroF1')) document.getElementById('modMacroF1').textContent = `${Math.round(data.evaluation_metrics.f1_macro * 1000) / 10}%`;
      if (document.getElementById('modAccuracy')) document.getElementById('modAccuracy').textContent = `${Math.round(data.evaluation_metrics.accuracy * 1000) / 10}%`;

      // Per-class metrics
      const cBody = document.getElementById('modClassMetricsBody');
      cBody.innerHTML = '';
      for (const [cls, m] of Object.entries(data.evaluation_metrics.per_class)) {
        cBody.innerHTML += `
          <tr>
            <td><strong>${cls}</strong></td>
            <td>${Math.round(m.recall * 1000) / 10}%</td>
            <td>${Math.round(m.precision * 1000) / 10}%</td>
            <td>${Math.round(m.f1 * 1000) / 10}%</td>
          </tr>
        `;
      }

      // Feature importances
      const fBox = document.getElementById('modFeatureImpContainer');
      fBox.innerHTML = '';
      if (data.feature_importances) {
        for (const [feat, imp] of Object.entries(data.feature_importances)) {
          const pct = Math.round(imp * 100);
          fBox.innerHTML += `
            <div style="font-size:13px;">
              <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
                <span>${feat}</span>
                <strong>${pct}%</strong>
              </div>
              <div style="background:#E5E7EB; border-radius:4px; height:8px; overflow:hidden;">
                <div style="background:var(--primary); height:100%; width:${pct}%;"></div>
              </div>
            </div>
          `;
        }
      }

      // Confusion matrix display
      const cmBox = document.getElementById('modConfusionMatrix');
      const cm = data.confusion_matrix.matrix;
      const labels = data.confusion_matrix.labels;
      let cmText = `Predicted ->   ${labels.join('   ')}\nActual:\n`;
      labels.forEach((lbl, idx) => {
        cmText += `${lbl.padEnd(12)}:   ${cm[idx].map(n => String(n).padStart(4)).join('    ')}\n`;
      });
      cmBox.innerHTML = `<pre style="margin:0; overflow-x:auto;">${cmText}</pre>`;
    } catch (e) {
      console.warn("Model status not available offline:", e);
      const cmBox = document.getElementById('modConfusionMatrix');
      if (cmBox) cmBox.innerHTML = `<div class="alert-box warning" style="margin:10px 0;">Model evaluation inspection requires an active connection to the MediConnect server.</div>`;
    }
  },

  async retrainModel() {
    if (!confirm("Retrain maternal risk classification model on the dataset?")) return;
    try {
      const res = await this.apiFetch('/api/model/retrain', { method: 'POST' });
      const data = await res.json();
      alert(`Model successfully retrained! Macro Recall: ${Math.round(data.metrics.recall_macro * 100)}%, High Risk Recall: ${Math.round(data.metrics.per_class['High Risk'].recall * 100)}%`);
      this.loadModelStatus();
    } catch (e) {
      alert("Retraining failed: " + e.message);
    }
  },

  // 13. Reports & Child Immunization Analytics (from XLS)
  async loadCoverageReports() {
    try {
      const res = await this.apiFetch('/api/analytics/coverage');
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      document.getElementById('repDistricts').textContent = data.dataset_info.total_districts;
      document.getElementById('repPentaDropout').textContent = `${data.aggregate_metrics.penta_dropout_rate_pct}%`;
      document.getElementById('repFullyImmunized').textContent = data.aggregate_metrics.total_fully_immunized_infants.toLocaleString();
      document.getElementById('repBcgTotal').textContent = data.aggregate_metrics.total_bcg_administered.toLocaleString();

      const sBody = document.getElementById('repStatesTableBody');
      sBody.innerHTML = '';
      data.top_states.forEach(st => {
        sBody.innerHTML += `
          <tr>
            <td><strong>${st.state}</strong></td>
            <td>${st.districts}</td>
            <td>${st.bcg.toLocaleString()}</td>
            <td>${st.penta_1.toLocaleString()}</td>
            <td>${st.penta_3.toLocaleString()}</td>
            <td><span class="badge ${st.dropout_pct > 10 ? 'badge-overdue' : 'badge-completed'}">${st.dropout_pct}%</span></td>
            <td><strong>${st.fully_immunized.toLocaleString()}</strong></td>
            <td>${st.asha_sessions.toLocaleString()}</td>
          </tr>
        `;
      });

      const dBody = document.getElementById('repDictTableBody');
      dBody.innerHTML = '';
      data.data_dictionary.forEach(d => {
        dBody.innerHTML += `
          <tr>
            <td><code>${d.code}</code></td>
            <td><strong>${d.title}</strong></td>
            <td>${d.description}</td>
          </tr>
        `;
      });
    } catch (e) {
      console.warn("Analytics not available offline:", e);
      const sBody = document.getElementById('repStatesTableBody');
      if (sBody) sBody.innerHTML = `<tr><td colspan="8" class="empty-state">State coverage analytics require an active server connection. Local child tracking remains available offline.</td></tr>`;
    }
  },

  // 14. Event Listeners Setup
  setupEventListeners() {
    // Navigation tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const view = tab.getAttribute('data-view');
        this.showView(view);
      });
    });

    // Forms
    document.getElementById('loginForm')?.addEventListener('submit', (e) => this.handleLogin(e));
    document.getElementById('signupForm')?.addEventListener('submit', (e) => this.handleSignup(e));
    document.getElementById('logoutBtn')?.addEventListener('click', () => this.logout());
    document.getElementById('addMotherForm')?.addEventListener('submit', (e) => this.handleAddMother(e));
    document.getElementById('maternalPredictForm')?.addEventListener('submit', (e) => this.handleMaternalPredict(e));
    document.getElementById('addChildForm')?.addEventListener('submit', (e) => this.handleAddChild(e));
    document.getElementById('recordVaccineForm')?.addEventListener('submit', (e) => this.handleRecordVaccine(e));
    document.getElementById('symptomForm')?.addEventListener('submit', (e) => this.handleAddSymptom(e));

    // Interactive Password Visibility Toggles
    this.setupPasswordToggles();

    // Language Selector Event Listener
    const langSelect = document.getElementById('langSelector');
    if (langSelect) {
      langSelect.value = window.i18n ? window.i18n.currentLang : 'bi';
      langSelect.addEventListener('change', (e) => {
        if (window.i18n) {
          window.i18n.setLanguage(e.target.value);
        }
      });
    }

    // Filters
    document.getElementById('motherSearchInput')?.addEventListener('input', () => this.loadMothers());
    document.getElementById('motherVillageFilter')?.addEventListener('change', () => this.loadMothers());
    document.getElementById('motherHighRiskFilter')?.addEventListener('change', () => this.loadMothers());

    // Global click delegation for View Schedule buttons
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-view-schedule, button[onclick*="showChildImmunizationDetails"]');
      if (btn) {
        const id = parseInt(btn.getAttribute('data-id')) || 0;
        const uid = btn.getAttribute('data-uid') || '';
        if (id || uid) {
          this.showChildImmunizationDetails(id, uid);
        }
      }
    });
  }
};

// Global window exposure for direct onclick calls
window.app = app;
window.showChildImmunizationDetails = (childId, clientUid) => app.showChildImmunizationDetails(childId, clientUid);

// Auto-run on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  app.init();
});
