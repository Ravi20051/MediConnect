/**
 * MediConnect Internationalization (i18n) Engine
 * Strict Single Language Support:
 *   - 'en': Pure English
 *   - 'hi': शुद्ध हिंदी (Pure Hindi)
 * Never mixes two languages together in the same element.
 */

const I18N_DICTIONARY = {
  // Brand & Header
  brand_title: {
    en: "MediConnect",
    hi: "मेडीकनेक्ट"
  },
  brand_subtitle: {
    en: "A Predictive EHR Companion for ASHA Workers in Low-Internet Rural Areas",
    hi: "ग्रामीण क्षेत्रों में आशा कार्यकर्ताओं के लिए स्वास्थ्य साथी"
  },
  network_online: {
    en: "Online",
    hi: "ऑनलाइन"
  },
  network_offline: {
    en: "Offline",
    hi: "ऑफलाइन"
  },
  btn_sim_offline: {
    en: "Simulate Offline",
    hi: "ऑफलाइन मोड"
  },
  btn_reconnect_online: {
    en: "Connect Online",
    hi: "ऑनलाइन कनेक्ट करें"
  },
  btn_logout: {
    en: "Logout",
    hi: "लॉगआउट"
  },

  // Navigation Tabs
  tab_dashboard: {
    en: "Dashboard",
    hi: "डैशबोर्ड"
  },
  tab_mothers: {
    en: "Mothers",
    hi: "माताएं"
  },
  tab_maternal_risk: {
    en: "Maternal Risk",
    hi: "मातृ जोखिम"
  },
  tab_children: {
    en: "Children",
    hi: "बच्चे"
  },
  tab_vaccine_followup: {
    en: "Vaccine Follow-up",
    hi: "टीकाकरण"
  },
  tab_outbreak_alerts: {
    en: "Outbreak Alerts",
    hi: "प्रकोप चेतावनी"
  },
  tab_record_symptom: {
    en: "Record Symptom",
    hi: "लक्षण दर्ज करें"
  },
  tab_sync_center: {
    en: "Sync Center",
    hi: "सिंक केंद्र"
  },
  tab_reports: {
    en: "Reports & Coverage",
    hi: "रिपोर्ट व कवरेज"
  },
  tab_model_status: {
    en: "Model Metrics",
    hi: "मॉडल मेट्रिक्स"
  },

  // Dashboard Banner & Actions
  greeting: {
    en: "Welcome",
    hi: "नमस्ते"
  },
  banner_desc: {
    en: "Field Health Companion for Sub-Center: {village}. Offline-capable data entry and local access in remote areas.",
    hi: "उप-स्वास्थ्य केंद्र {village} के लिए स्वास्थ्य साथी। दूरदराज क्षेत्रों में ऑफलाइन प्रविष्टि और स्थानीय पहुंच उपलब्ध है।"
  },
  btn_add_mother: {
    en: "Add Mother",
    hi: "गर्भवती महिला जोड़ें"
  },
  btn_check_risk: {
    en: "Check Risk",
    hi: "जोखिम जांचें"
  },
  btn_add_child: {
    en: "Add Child",
    hi: "शिशु पंजीकरण"
  },
  btn_followup: {
    en: "Vaccine Follow-up",
    hi: "टीकाकरण सूची"
  },
  btn_record_symptom: {
    en: "Record Symptom",
    hi: "लक्षण दर्ज करें"
  },
  btn_outbreak_alerts: {
    en: "Outbreak Alerts",
    hi: "प्रकोप चेतावनी"
  },
  btn_sync_now: {
    en: "Sync Now",
    hi: "डेटा सिंक करें"
  },

  // KPIs
  kpi_mothers: {
    en: "Registered Mothers",
    hi: "पंजीकृत माताएं"
  },
  kpi_mothers_sub: {
    en: "Total enrolled pregnant women",
    hi: "कुल पंजीकृत गर्भवती महिलाएं"
  },
  kpi_high_risk: {
    en: "High-Risk Cases",
    hi: "उच्च जोखिम मामले"
  },
  kpi_high_risk_sub: {
    en: "Immediate referral required",
    hi: "तत्काल अस्पताल रेफरल आवश्यक"
  },
  kpi_children: {
    en: "Children Tracked",
    hi: "निगरानी में कुल बच्चे"
  },
  kpi_children_sub: {
    en: "Immunization surveillance active",
    hi: "नियमित टीकाकरण निगरानी में"
  },
  kpi_vaccines: {
    en: "Vaccines Due / Overdue",
    hi: "लंबित टीके"
  },
  kpi_vaccines_sub: {
    en: "Actionable follow-up required",
    hi: "गृह भेंट व परामर्श आवश्यक"
  },
  kpi_alerts: {
    en: "Outbreak Alerts",
    hi: "सक्रिय बीमारी चेतावनी"
  },
  kpi_alerts_sub: {
    en: "Unusual symptom clusters detected",
    hi: "असामान्य लक्षण क्लस्टर मिले"
  },
  kpi_sync: {
    en: "Sync Status",
    hi: "सिंक स्थिति"
  },

  // Maternal Form & Labels
  maternal_title: {
    en: "Maternal Health Risk Prediction",
    hi: "मातृ स्वास्थ्य जोखिम पूर्वानुमान"
  },
  maternal_subtitle: {
    en: "Trained on genuine clinical data using the exact 6 features.",
    hi: "वास्तविक क्लिनिकल डेटा के 6 मापकों पर प्रशिक्षित मॉडल।"
  },
  label_age: {
    en: "1. Age in Years [10-70]",
    hi: "1. उम्र (वर्ष में)"
  },
  label_sbp: {
    en: "2. Systolic Blood Pressure (mmHg) [70-160]",
    hi: "2. ऊपर का रक्तचाप (सिस्टोलिक BP)"
  },
  label_dbp: {
    en: "3. Diastolic Blood Pressure (mmHg) [49-100]",
    hi: "3. नीचे का रक्तचाप (डायस्टोलिक BP)"
  },
  label_bs: {
    en: "4. Blood Sugar / Glucose (mmol/L) [6.0-19.0]",
    hi: "4. रक्त में शर्करा (ब्लड शुगर)"
  },
  label_temp: {
    en: "5. Body Temperature (°F) [98.0-103.0]",
    hi: "5. शरीर का तापमान (फारेनहाइट)"
  },
  label_hr: {
    en: "6. Heart Rate (BPM) [60-120]",
    hi: "6. हृदय गति (नाड़ी दर)"
  },
  btn_predict_risk: {
    en: "Predict Risk Level",
    hi: "जोखिम का स्तर जांचें"
  },

  // Child Immunization
  imm_title: {
    en: "Weekly Actionable Immunization Follow-Up",
    hi: "साप्ताहिक टीकाकरण फॉलो-अप कार्यसूची"
  },
  imm_notice_title: {
    en: "ASHA Weekly Field Action",
    hi: "आशा कार्यकर्ता साप्ताहिक कार्य"
  },
  imm_notice_desc: {
    en: "Visit families with High Priority / Overdue status before the upcoming session. Counsel parents on routine immunization to prevent dropout.",
    hi: "आगामी सत्र से पहले बकाया बच्चों के घर जाकर परिजनों को टीका लगवाने हेतु प्रेरित करें।"
  },

  // Disease Outbreak
  outbreak_title: {
    en: "Village-Level Disease Outbreak Early Warning",
    hi: "ग्राम स्तरीय बीमारी प्रकोप प्रारंभिक चेतावनी"
  },

  // Sync Center
  sync_title: {
    en: "Offline Storage & Synchronization Gateway",
    hi: "ऑफलाइन डेटा संग्रहण एवं सिंक केंद्र"
  },
  sync_pending_label: {
    en: "Pending Offline Records",
    hi: "लंबित ऑफलाइन रिकॉर्ड"
  },
  sync_last_label: {
    en: "Last Successful Sync",
    hi: "अंतिम सफल सिंक"
  },
  sync_network_label: {
    en: "Device Network State",
    hi: "डिवाइस नेटवर्क स्थिति"
  },

  // Login
  login_title: {
    en: "ASHA Worker Login",
    hi: "आशा कार्यकर्ता लॉगिन"
  },
  login_user_label: {
    en: "Username",
    hi: "यूजरनेम"
  },
  login_pwd_label: {
    en: "Password",
    hi: "पासवर्ड"
  },
  login_btn: {
    en: "Login to Field App",
    hi: "लॉगिन करें"
  }
};

class I18nManager {
  constructor() {
    let saved = localStorage.getItem('mc_lang');
    if (!saved || !['en', 'hi'].includes(saved)) {
      saved = 'en'; // Clean pure English default
    }
    this.currentLang = saved;
  }

  setLanguage(lang) {
    if (!['en', 'hi'].includes(lang)) lang = 'en';
    this.currentLang = lang;
    localStorage.setItem('mc_lang', lang);
    this.applyTranslations();
  }

  get(key, vars = {}) {
    const entry = I18N_DICTIONARY[key];
    if (!entry) return key;
    let text = entry[this.currentLang] || entry['en'] || key;
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, v);
    }
    return text;
  }

  applyTranslations() {
    // 1. Elements with data-i18n
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      el.textContent = this.get(key);
    });

    // 2. Brand Titles
    const brandTitle = document.querySelector('.brand-titles h1');
    if (brandTitle) brandTitle.textContent = this.get('brand_title');

    const brandSub = document.querySelector('.brand-titles .subtitle');
    if (brandSub) brandSub.textContent = this.get('brand_subtitle');

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.textContent = this.get('btn_logout');

    // 3. Navigation Tabs
    const tabMap = {
      'dashboard': { icon: '📊', key: 'tab_dashboard' },
      'mothers': { icon: '🤰', key: 'tab_mothers' },
      'maternal-predict': { icon: '🩺', key: 'tab_maternal_risk' },
      'children': { icon: '👶', key: 'tab_children' },
      'immunization-followup': { icon: '💉', key: 'tab_vaccine_followup' },
      'outbreak-alerts': { icon: '🚨', key: 'tab_outbreak_alerts' },
      'symptom-entry': { icon: '📝', key: 'tab_record_symptom' },
      'sync-center': { icon: '🔄', key: 'tab_sync_center' },
      'reports': { icon: '📈', key: 'tab_reports' },
      'model-status': { icon: '⚙️', key: 'tab_model_status' }
    };

    for (const [vName, config] of Object.entries(tabMap)) {
      const btn = document.querySelector(`.nav-tab[data-view="${vName}"]`);
      if (btn) {
        const span = btn.querySelector('span:not(.tab-badge)');
        if (span) span.textContent = this.get(config.key);
      }
    }

    // 4. Action Banner Greeting
    const greetingEl = document.getElementById('dashGreetingText');
    if (greetingEl) {
      greetingEl.textContent = this.get('greeting');
    }

    // 5. Quick Buttons - Strictly Single Language!
    const quickButtons = [
      { id: 'btnQuickAddMother', key: 'btn_add_mother', icon: '➕ 🤰' },
      { id: 'btnQuickCheckRisk', key: 'btn_check_risk', icon: '🩺' },
      { id: 'btnQuickAddChild', key: 'btn_add_child', icon: '➕ 👶' },
      { id: 'btnQuickFollowup', key: 'btn_followup', icon: '💉' },
      { id: 'btnQuickRecordSym', key: 'btn_record_symptom', icon: '📝' },
      { id: 'btnQuickAlerts', key: 'btn_outbreak_alerts', icon: '🚨' },
      { id: 'btnQuickSync', key: 'btn_sync_now', icon: '🔄' }
    ];

    quickButtons.forEach(item => {
      const btn = document.getElementById(item.id);
      if (btn) {
        btn.innerHTML = `<span>${item.icon} ${this.get(item.key)}</span>`;
      }
    });

    // 6. Network status & toggle button
    if (window.app) {
      const isOnline = window.app.isOnline;
      const text = document.getElementById('networkText');
      if (text) {
        text.textContent = isOnline ? this.get('network_online') : this.get('network_offline');
      }
      const toggleBtn = document.getElementById('toggleNetworkBtn');
      if (toggleBtn) {
        toggleBtn.textContent = isOnline ? this.get('btn_sim_offline') : this.get('btn_reconnect_online');
      }
    }

    // 7. Sync Now Button
    const syncBtn = document.getElementById('syncNowBtn');
    if (syncBtn) syncBtn.textContent = this.get('btn_sync_now');

    // 8. Predict Button
    const predBtn = document.getElementById('btnSubmitPredict');
    if (predBtn) predBtn.textContent = this.get('btn_predict_risk');

    // 9. Sync dropdown selection
    const langSelect = document.getElementById('langSelector');
    if (langSelect && langSelect.value !== this.currentLang) {
      langSelect.value = this.currentLang;
    }
  }
}

const i18n = new I18nManager();
window.i18n = i18n;
