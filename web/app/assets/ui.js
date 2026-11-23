// ============================================================
// Composants UI partagés — refonte conviviale (2026-11)
// Cartes marché, puces de secteur, échéances "Dépôt avant le…".
// Chargé après data.js + icons.js, avant le script de page.
// ============================================================
(function(){
  // Secteurs métier : mot-clé -> icône + couleur d'accent + libellé court
  var SEC = [
    { k:['BTP','Construction','Génie'],                         icon:'hammer',                 col:'#d97706', short:'BTP & Construction' },
    { k:['Santé','Médical','Pharmacie'],                        icon:'heart-pulse',            col:'#e11d48', short:'Santé' },
    { k:['Eau','Forages','Assainissement'],                     icon:'droplet',                col:'#0284c7', short:'Eau & Forages' },
    { k:['Informatique','Télécom'],                             icon:'cpu',                    col:'#7c3aed', short:'Informatique' },
    { k:['Véhicules','Transports','Hydrocarbures','Carburant'], icon:'truck',                  col:'#ea580c', short:'Transport' },
    { k:['Énergie','lectricité'],                               icon:'zap',                    col:'#ca8a04', short:'Énergie' },
    { k:['Mobilier','Bureau'],                                  icon:'armchair',               col:'#c026d3', short:'Mobilier' },
    { k:['Agréments','Répertoires','Fournisseurs'],             icon:'clipboard-list',         col:'#0d9488', short:'Agréments' },
    { k:['Gardiennage','Sécurité'],                             icon:'shield',                 col:'#64748b', short:'Sécurité' },
    { k:['Études','Audit','Conseil'],                           icon:'chart-no-axes-column',   col:'#4f46e5', short:'Études & Conseil' },
    { k:['Agriculture','Élevage','Forêt'],                      icon:'sprout',                 col:'#16a34a', short:'Agriculture' },
    { k:['Restauration','Événementiel'],                        icon:'utensils',               col:'#db2777', short:'Restauration' },
    { k:['Services Généraux','Divers'],                         icon:'package',                col:'#64748b', short:'Services divers' }
  ];
  var DEF = { icon:'tag', col:'#15603d', short:'Marché public' };

  window.sectorMeta = function(name){
    if(!name) return DEF;
    for(var i=0;i<SEC.length;i++){ for(var j=0;j<SEC[i].k.length;j++){ if(name.indexOf(SEC[i].k[j])>-1) return SEC[i]; } }
    return DEF;
  };

  window.typeCls = function(t){ return t==='AO'?'type-tender':((t==='RP'||t==='result')?'type-result':'type-price'); };

  window.cleanVal = function(v, fb){
    if(v==null) return fb||'—';
    var s=(''+v).trim(), l=s.toLowerCase();
    if(!s || l==='null' || l==='none' || l==='undefined') return fb||'—';
    return s;
  };

  // Information d'échéance, formulée de manière chaleureuse et claire
  window.deadlineInfo = function(m){
    if(m.status==='result') return { cls:'result', icon:'badge-check', text:'Résultat publié', sub:(m.deadline?window.fmtDate(m.deadline):'') };
    if(!m.deadline) return { cls:'neutral', icon:'calendar', text:'Dépôt selon le dossier', sub:'' };
    var d=window.daysLeft(m.deadline), dateStr=window.cleanVal(m.deadline_raw, window.fmtDate(m.deadline));
    if(d<0)   return { cls:'closed', icon:'lock',           text:'Dépôt clôturé',   sub:'le '+dateStr };
    if(d===0) return { cls:'urgent', icon:'triangle-alert', text:'Dernier jour !',  sub:dateStr };
    if(d<=3)  return { cls:'urgent', icon:'clock',          text:'Plus que '+d+' jour'+(d>1?'s':''), sub:'· '+dateStr };
    if(d<=10) return { cls:'soon',   icon:'clock',          text:'Avant le '+dateStr, sub:'J-'+d };
    return      { cls:'open',   icon:'calendar',       text:'Avant le '+dateStr, sub:'' };
  };
  window.deadlinePill = function(m){
    var i=window.deadlineInfo(m);
    return '<span class="deadline-pill '+i.cls+'"><i data-icon="'+i.icon+'" data-size="13"></i> '+i.text+(i.sub?' <em>'+i.sub+'</em>':'')+'</span>';
  };

  window.sectorChip = function(name){
    if(!name) return '';
    var s=window.sectorMeta(name);
    return '<span class="sector-chip" style="--sec:'+s.col+'"><i data-icon="'+s.icon+'" data-size="12"></i> '+s.short+'</span>';
  };

  window.marketAmount = function(m){
    if(m.amount) return '<span class="mk-card-amount">'+window.fmtAmount(m.amount)+'</span>';
    var n=(m.detail_lots&&m.detail_lots.length)||m.lots||1;
    if(n>1) return '<span class="mk-card-amount">'+n+' lots<small>montant au dossier</small></span>';
    return '<span class="mk-card-amount" style="font-weight:600;color:var(--muted)">Selon dossier</span>';
  };

  // Carte marché conviviale (utilisée par dashboard, marchés, recherche, autorité)
  window.marketCard = function(m){
    var title=window.cleanVal(m.title,'Avis de marché public');
    var auth=window.cleanVal(m.authority,'Autorité contractante');
    var href='market.html?id='+encodeURIComponent(m.id);
    return '<a class="mk-card" href="'+href+'">'
      +'<div class="mk-card-top"><span class="mk-type '+window.typeCls(m.type)+'"><i data-icon="tag" data-size="11"></i> '+window.cleanVal(m.typeLabel,'Avis')+'</span>'+window.sectorChip(m.sector)+'</div>'
      +'<div class="mk-card-title">'+title+'</div>'
      +'<div class="mk-card-auth"><i data-icon="landmark" data-size="13"></i><span>'+auth+'</span></div>'
      +'<div class="mk-card-bottom">'+window.deadlinePill(m)+window.marketAmount(m)+'</div>'
      +'</a>';
  };

  // Tuile de secteur (grille d'exploration)
  window.sectorTile = function(name, count){
    var s=window.sectorMeta(name);
    return '<a class="sector-tile" style="--sec:'+s.col+'" href="markets.html?sector='+encodeURIComponent(name)+'">'
      +'<div class="sec-ico"><i data-icon="'+s.icon+'" data-size="20"></i></div>'
      +'<div class="sec-body"><span class="sec-name" title="'+name+'">'+name+'</span><span class="sec-count"><b>'+count+'</b> marché'+(count>1?'s':'')+'</span></div></a>';
  };
})();
