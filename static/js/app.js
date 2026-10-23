(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const $ = (selector, root = document) => root.querySelector(selector);
  const toast = (message, error = false) => {
    const node = $('#toast'); if (!node) return;
    node.textContent = message; node.classList.toggle('error', error); node.classList.add('show');
    window.clearTimeout(node.timer); node.timer = window.setTimeout(() => node.classList.remove('show'), 3600);
  };
  const api = async (url, options = {}) => {
    const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'The request could not be completed.');
    return body;
  };

  const theme = () => document.documentElement.dataset.theme;
  const updateToggle = () => {
    const toggle = $('#theme-toggle'); if (!toggle) return;
    const dark = theme() === 'dark'; toggle.innerHTML = `<span aria-hidden="true">${dark ? '☀' : '☾'}</span>`;
    toggle.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} mode`);
  };
  $('#theme-toggle')?.addEventListener('click', () => { document.documentElement.dataset.theme = theme() === 'dark' ? 'light' : 'dark'; localStorage.setItem('citycare-theme', theme()); updateToggle(); renderCharts(); });
  updateToggle();
  $('[data-menu]')?.addEventListener('click', () => $('#sidebar')?.classList.toggle('open'));

  let charts = [];
  const renderCharts = () => {
    if (!window.Chart) return;
    charts.forEach(chart => chart.destroy()); charts = [];
    const style = getComputedStyle(document.documentElement), dark = theme() === 'dark';
    document.querySelectorAll('canvas[data-chart]').forEach(canvas => {
      const labels = JSON.parse(canvas.dataset.labels || '[]'), values = JSON.parse(canvas.dataset.values || '[]');
      const colors = [style.getPropertyValue('--navy').trim(), style.getPropertyValue('--accent').trim(), '#10B981', '#F59E0B', '#64748B', '#5EEAD4', '#EF4444'];
      charts.push(new Chart(canvas, { type: canvas.dataset.chart === 'horizontal' ? 'bar' : canvas.dataset.chart,
        data: { labels, datasets: [{ data: values, backgroundColor: canvas.dataset.chart === 'bar' || canvas.dataset.chart === 'horizontal' ? colors[0] : colors, borderRadius: 6, borderWidth: 0 }] },
        options: { indexAxis: canvas.dataset.chart === 'horizontal' ? 'y' : 'x', maintainAspectRatio: false, plugins: { legend: { display: canvas.dataset.chart === 'doughnut', labels: { color: style.getPropertyValue('--text').trim(), boxWidth: 10 } } }, scales: canvas.dataset.chart === 'doughnut' ? {} : { x: { ticks: { color: style.getPropertyValue('--muted').trim() }, grid: { color: dark ? '#374151' : '#E2E8F0' } }, y: { beginAtZero: true, ticks: { color: style.getPropertyValue('--muted').trim() }, grid: { color: dark ? '#374151' : '#E2E8F0' } } } } }));
    });
  };
  window.addEventListener('load', renderCharts);

  const question = $('#question'), faqForm = $('#faq-form'), conversation = $('#conversation');
  const addChat = (type, heading, text, trace) => {
    const item = document.createElement('article'); item.className = `chat ${type}`;
    const name = document.createElement('b'); name.textContent = heading; const paragraph = document.createElement('p'); paragraph.textContent = text;
    item.append(name, paragraph);
    if (trace) { const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'How was this answer derived?'; const pre = document.createElement('pre'); pre.textContent = trace; const copy = document.createElement('button'); copy.className = 'text-button'; copy.type = 'button'; copy.textContent = 'Copy answer'; copy.addEventListener('click', () => navigator.clipboard?.writeText(text).then(() => toast('Answer copied.'))); details.append(summary, pre, copy); item.append(details); }
    conversation?.append(item); conversation?.scrollTo({ top: conversation.scrollHeight, behavior: 'smooth' });
  };
  const sendQuestion = async value => {
    const text = value.trim(); if (!text) return;
    addChat('user', 'You', text); question.value = ''; const pending = document.createElement('article'); pending.className = 'chat assistant'; pending.textContent = 'CityCare Assistant is checking the knowledge base…'; conversation.append(pending);
    try { const result = await api('/api/faq', { method: 'POST', body: JSON.stringify({ question: text }) }); pending.remove(); addChat('assistant', result.found ? 'CityCare Assistant' : 'No conclusion derived', result.answer, result.trace); }
    catch (error) { pending.remove(); addChat('assistant', 'Unable to process question', error.message); }
  };
  faqForm?.addEventListener('submit', event => { event.preventDefault(); sendQuestion(question.value); });
  question?.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); faqForm.requestSubmit(); } });
  document.querySelectorAll('[data-suggestion]').forEach(button => button.addEventListener('click', () => { question.value = button.dataset.suggestion; faqForm.requestSubmit(); }));
  $('#clear-chat')?.addEventListener('click', () => { conversation.innerHTML = ''; addChat('assistant', 'CityCare Assistant', 'Conversation cleared. What would you like to know?'); });
  if (question && new URLSearchParams(location.search).get('q')) { question.value = new URLSearchParams(location.search).get('q'); question.focus(); }

  const directorySearch = $('#directory-search'); directorySearch?.addEventListener('input', () => { let shown = 0; document.querySelectorAll('#directory-grid .directory-card').forEach(card => { const show = card.dataset.search.includes(directorySearch.value.toLowerCase()); card.hidden = !show; shown += Number(show); }); $('#directory-count').textContent = `${shown} result${shown === 1 ? '' : 's'}`; });

  const factSearch = $('#fact-search'), predicateFilter = $('#predicate-filter');
  const filterFacts = () => document.querySelectorAll('#facts-table tbody tr').forEach(row => { const query = factSearch.value.toLowerCase(), predicate = predicateFilter.value; row.hidden = (predicate && row.dataset.predicate !== predicate) || !row.textContent.toLowerCase().includes(query); });
  factSearch?.addEventListener('input', filterFacts); predicateFilter?.addEventListener('change', filterFacts);
  const dialog = $('#fact-dialog'), factForm = $('#fact-form');
  const openFact = row => { $('#fact-index').value = row?.dataset.index ?? ''; $('#fact-predicate').value = row?.children[1]?.textContent.trim() ?? ''; const args = row?.children[2]?.textContent.split(', ').map(a => a.trim()) ?? []; $('#fact-arg-one').value = args[0] ?? ''; $('#fact-arg-two').value = args.slice(1).join(', ') ?? ''; $('#fact-dialog-title').textContent = row ? 'Edit fact' : 'Add fact'; dialog.showModal(); };
  $('#new-fact')?.addEventListener('click', () => openFact()); document.querySelectorAll('.edit-fact').forEach(button => button.addEventListener('click', () => openFact(button.closest('tr'))));
  factForm?.addEventListener('submit', async event => { event.preventDefault(); const index = $('#fact-index').value, args = [$('#fact-arg-one').value, $('#fact-arg-two').value]; try { await api(index === '' ? '/api/facts' : `/api/facts/${index}`, { method: index === '' ? 'POST' : 'PUT', body: JSON.stringify({ predicate: $('#fact-predicate').value, args }) }); location.reload(); } catch (error) { toast(error.message, true); } });
  document.querySelectorAll('.delete-fact').forEach(button => button.addEventListener('click', async () => { const row = button.closest('tr'); if (!confirm(`Delete ${row.children[1].textContent}(${row.children[2].textContent})?`)) return; try { await api(`/api/facts/${row.dataset.index}`, { method: 'DELETE' }); location.reload(); } catch (error) { toast(error.message, true); } }));
  document.querySelectorAll('[data-admin-action]').forEach(button => button.addEventListener('click', async () => { try { const answer = await api(`/api/admin/${button.dataset.adminAction}`, { method: 'POST' }); $('#admin-status').textContent = answer.message + (answer.filename ? ` ${answer.filename}` : ''); toast(answer.message); } catch (error) { toast(error.message, true); } }));
  $('#test-query')?.addEventListener('click', async () => { const result = $('#query-result'); try { const answer = await api('/api/admin/query', { method: 'POST', body: JSON.stringify({ query: $('#logical-query').value }) }); result.textContent = answer.answers.length ? JSON.stringify(answer.answers, null, 2) : `No result: nothing can be derived for ${answer.query}`; } catch (error) { result.textContent = error.message; } });
  $('#toggle-password')?.addEventListener('click', event => { const input = $('#password'); const reveal = input.type === 'password'; input.type = reveal ? 'text' : 'password'; event.currentTarget.textContent = reveal ? 'Hide' : 'Show'; });
  $('#account-form')?.addEventListener('submit', async event => { event.preventDefault(); const button = event.currentTarget.querySelector('button'); button.disabled = true; try { const response = await api('/api/admin/users', { method: 'POST', body: JSON.stringify({ username: $('#account-username').value, role: $('#account-role').value, password: $('#account-password').value }) }); toast(response.message); event.currentTarget.reset(); setTimeout(() => location.reload(), 450); } catch (error) { toast(error.message, true); button.disabled = false; } });
  const publicMenu = $('#public-menu');
  $('[data-public-menu]')?.addEventListener('click', event => { const open = publicMenu.classList.toggle('open'); event.currentTarget.setAttribute('aria-expanded', String(open)); });
  const siteSearch = $('#site-search-input'), searchResults = $('#site-search-results');
  if (siteSearch && searchResults) {
    const pages = [{ name: 'Home', href: '/' }, { name: 'About the Project', href: '/about' }, { name: 'Features', href: '#features' }, { name: 'How It Works', href: '#how-it-works' }, { name: 'FAQ Assistant', href: '/faq' }, { name: 'Doctors', href: '/doctors' }, { name: 'Departments', href: '/departments' }, { name: 'Services & Facilities', href: '/services' }];
    let searchable = pages;
    fetch('/api/directory').then(response => response.ok ? response.json() : null).then(data => { if (!data) return; const directories = [...(data.doctors || []), ...(data.departments || []), ...(data.services || []), ...(data.facilities || [])].map(item => ({ name: item.name, href: item.kind === 'Service' || item.kind === 'Facility' ? '/services' : item.specialty !== undefined ? '/doctors' : '/departments' })); searchable = [...pages, ...directories]; }).catch(() => {});
    siteSearch.addEventListener('input', () => { const query = siteSearch.value.trim().toLowerCase(); if (!query) { searchResults.hidden = true; return; } const matches = searchable.filter(item => item.name.toLowerCase().includes(query)).slice(0, 7); searchResults.innerHTML = ''; if (!matches.length) { const message = document.createElement('p'); message.textContent = 'No matching CityCare information found.'; searchResults.append(message); } else { matches.forEach(item => { const link = document.createElement('a'); link.href = item.href; link.textContent = item.name; searchResults.append(link); }); } searchResults.hidden = false; });
    document.addEventListener('click', event => { if (!event.target.closest('.site-search')) searchResults.hidden = true; });
  }
})();
