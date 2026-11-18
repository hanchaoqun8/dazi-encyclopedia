// 微信私域弹窗
function openQR(){var o=document.getElementById('qrOverlay');if(o)o.classList.add('open');}
function closeQR(e){var o=document.getElementById('qrOverlay');if(!o)return;if(!e||e.target===o||e.target.classList.contains('qr-close'))o.classList.remove('open');}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeQR();});
