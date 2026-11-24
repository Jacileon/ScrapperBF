// auth.js — parcours d'authentification réel (inscription / connexion / mot de passe oublié).
// S'appuie sur window.VBF (session.js). Chaque <form data-auth="login|register|forgot">
// contient des champs nommés et un conteneur [data-error] pour les messages.
(function(){
  function qp(name){ try { return new URLSearchParams(location.search).get(name); } catch(e){ return null; } }

  function showError(form, msg){
    var box = form.querySelector('[data-error]');
    if (box){ box.textContent = msg; box.hidden = false; }
  }
  function clearError(form){
    var box = form.querySelector('[data-error]');
    if (box){ box.hidden = true; box.textContent=''; }
  }
  function val(form, name){ var f = form.querySelector('[name="'+name+'"]'); return f ? f.value.trim() : ''; }

  function setLoading(btn, on){
    if (!btn) return;
    if (on){ btn.dataset._label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Veuillez patienter…'; }
    else { btn.disabled = false; if (btn.dataset._label) btn.innerHTML = btn.dataset._label; }
  }

  function humanError(err){
    if (err && err.data){
      var d = err.data.detail;
      if (typeof d === 'string') return d;
      if (d && d.message) return d.message;
      if (Array.isArray(d) && d[0] && d[0].msg) return d[0].msg;
    }
    return "Une erreur est survenue. Réessayez.";
  }

  document.querySelectorAll('form[data-auth]').forEach(function(form){
    form.addEventListener('submit', function(e){
      e.preventDefault();
      clearError(form);
      var kind = form.dataset.auth;
      var btn = form.querySelector('button[type=submit]');
      setLoading(btn, true);

      var done = function(){ setLoading(btn, false); };
      var fail = function(err){ done(); showError(form, humanError(err)); };

      if (kind === 'login'){
        window.VBF.api('/api/auth/login', {body:{email:val(form,'email'), password:val(form,'password')}})
          .then(function(){ location.href = qp('next') || 'dashboard.html'; })
          .catch(fail);
      } else if (kind === 'register'){
        window.VBF.api('/api/auth/register', {body:{
          email:val(form,'email'), password:val(form,'password'),
          nom:val(form,'nom'), organisation:val(form,'organisation'), telephone:val(form,'telephone')
        }})
          .then(function(){ location.href = qp('next') || 'dashboard.html'; })
          .catch(fail);
      } else if (kind === 'forgot'){
        window.VBF.api('/api/auth/forgot-password', {body:{email:val(form,'email')}})
          .then(function(d){
            done();
            var ok = form.querySelector('[data-success]');
            if (ok){ ok.textContent = (d && d.message) || 'Vérifiez votre boîte mail.'; ok.hidden = false; }
            form.querySelectorAll('input,button').forEach(function(x){ x.disabled = true; });
          })
          .catch(fail);
      }
    });
  });

  // Si déjà connecté, proposer d'aller au tableau de bord depuis login/register.
  var hint = document.querySelector('[data-already]');
  if (hint && window.VBF){
    window.VBF.me().then(function(u){ if (u){ hint.hidden = false; } });
  }
})();
