/* Lichte, veilige markdown-renderer voor de AI-antwoordbubbel. Escape EERST (geen
   XSS), render dan een subset: koppen, bold/italic/code, lijsten, hr, alinea's.
   Bewust klein — geen dependency, geen buildpipeline. */
(function () {
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function inline(s) {
    return s
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }
  function render(text) {
    var lines = String(text || '').replace(/\r/g, '').split('\n');
    var out = '', inList = false;
    function closeList() { if (inList) { out += '</ul>'; inList = false; } }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (t === '') { closeList(); continue; }
      if (/^---+$/.test(t) || /^___+$/.test(t)) { closeList(); out += '<hr>'; continue; }
      var h = t.match(/^(#{1,4})\s+(.*)$/);
      if (h) { closeList(); var lvl = h[1].length; out += '<h' + lvl + '>' + inline(esc(h[2])) + '</h' + lvl + '>'; continue; }
      var li = t.match(/^[-*]\s+(.*)$/);
      if (li) { if (!inList) { out += '<ul>'; inList = true; } out += '<li>' + inline(esc(li[1])) + '</li>'; continue; }
      closeList();
      out += '<p>' + inline(esc(t)) + '</p>';
    }
    closeList();
    return out;
  }
  window.dwvRenderMarkdown = render;
  window.dwvFormatBubble = function (el) {
    if (!el) return;
    var raw = el.textContent;
    if (!raw || !raw.trim()) return;
    try { el.innerHTML = render(raw); el.classList.add('md-rendered'); } catch (e) {}
  };
})();
