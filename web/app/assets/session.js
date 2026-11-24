// session.js — client API + session partagée pour tout le front Veille BF.
// Expose window.VBF : appels API (cookies inclus), utilisateur courant, helpers d'offre.
(function(){
  var ORDER = ['gratuit','pro','entreprise'];

  function api(path, opts){
    opts = opts || {};
    var cfg = {
      method: opts.method || (opts.body ? 'POST' : 'GET'),
      credentials: 'include',
      headers: Object.assign({'Content-Type':'application/json'}, opts.headers||{})
    };
    if (opts.body !== undefined && opts.body !== null) cfg.body = JSON.stringify(opts.body);
    return fetch(path, cfg).then(function(r){
      var ct = r.headers.get('content-type')||'';
      var parse = ct.indexOf('application/json') > -1 ? r.json() : r.text();
      return parse.then(function(data){
        if (!r.ok){ var e = new Error('HTTP '+r.status); e.status=r.status; e.data=data; throw e; }
        return data;
      });
    });
  }

  var _mePromise = null;
  function me(force){
    if (_mePromise && !force) return _mePromise;
    _mePromise = api('/api/auth/me').then(function(d){ return d.user; }).catch(function(){ return null; });
    return _mePromise;
  }

  function planRank(id){ var i = ORDER.indexOf((id||'gratuit')); return i < 0 ? 0 : i; }
  function hasFeature(user, feat){ return !!(user && user.plan && user.plan.features && user.plan.features[feat]); }
  function planAtLeast(user, min){ return planRank(user && user.plan_id) >= planRank(min); }

  function logout(){
    return api('/api/auth/logout', {method:'POST', body:{}}).then(function(){
      _mePromise = null;
      location.href = 'login.html';
    });
  }

  function fmtFcfa(n){
    n = Number(n)||0;
    return n.toLocaleString('fr-FR') + ' FCFA';
  }

  // Protège l'accès à une page : si l'utilisateur n'a pas la capacité, affiche un
  // écran d'invitation à l'upgrade par-dessus le contenu. Renvoie une promesse -> user|null.
  function gate(feature, opts){
    opts = opts || {};
    return me().then(function(user){
      if (!user){ // non connecté
        showOverlay({
          titre: 'Connectez-vous pour continuer',
          texte: 'Cette section est réservée aux membres. Connectez-vous ou créez un compte gratuit.',
          actions: '<a class="button" href="login.html">Se connecter</a>'
               + '<a class="button ghost" href="register.html">Créer un compte</a>'
        });
        return null;
      }
      if (hasFeature(user, feature)) return user;
      showOverlay({
        titre: (opts.titre || 'Passez à une offre supérieure'),
        texte: (opts.texte || "Cette fonctionnalité est incluse dans les offres Pro et Entreprise."),
        actions: '<a class="button" href="pricing.html">Voir les offres</a>'
             + '<a class="button ghost" href="dashboard.html">Retour à l\'accueil</a>'
      });
      return null;
    });
  }

  function showOverlay(o){
    var el = document.createElement('div');
    el.className = 'vbf-gate-overlay';
    el.innerHTML =
      '<div class="vbf-gate-card">'
      + '<div class="vbf-gate-ico"><i data-icon="lock" data-size="28"></i></div>'
      + '<h2>'+o.titre+'</h2><p>'+o.texte+'</p>'
      + '<div class="vbf-gate-actions">'+o.actions+'</div>'
      + '</div>';
    document.body.appendChild(el);
    if (window.renderIcons) window.renderIcons(el);
  }

  window.VBF = {
    api: api, me: me, logout: logout,
    planRank: planRank, hasFeature: hasFeature, planAtLeast: planAtLeast,
    fmtFcfa: fmtFcfa, gate: gate, ORDER: ORDER
  };
})();
