/* Archive page: post fetching, search, render */

const API = '';
let allPosts = [];
let userStatus = null; // null = not logged in, 'inactive', or 'active'

// ── Bootstrap ─────────────────────────────────────────────────────────────

async function init() {
  document.getElementById('archiveContent').style.display = 'block';

  const token = localStorage.getItem('hsk_token');
  if (token) {
    try {
      const meRes = await fetch(`${API}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (meRes.ok) {
        const user = await meRes.json();
        userStatus = user.subscription_status;
        document.getElementById('signOutBtn').style.display = 'inline-block';
        const greeting = document.getElementById('userGreeting');
        if (greeting) greeting.textContent = `Hi, ${user.name.split(' ')[0]}`;
      } else if (meRes.status === 401) {
        localStorage.removeItem('hsk_token');
      }
    } catch (_) { /* non-fatal — still show titles */ }
  }

  await loadPosts();
}

// ── Posts ─────────────────────────────────────────────────────────────────

async function loadPosts() {
  try {
    const res = await fetch(`${API}/api/posts`);

    if (!res.ok) {
      document.getElementById('loadingState').style.display = 'none';
      document.getElementById('emptyState').style.display = 'block';
      document.getElementById('emptyState').querySelector('p').textContent =
        'Could not load posts. Please refresh the page.';
      return;
    }

    allPosts = await res.json();
    document.getElementById('loadingState').style.display = 'none';
    renderPosts(allPosts);

  } catch (err) {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('emptyState').style.display = 'block';
  }
}

function renderPosts(posts) {
  const grid  = document.getElementById('postsGrid');
  const empty = document.getElementById('emptyState');

  grid.innerHTML = '';

  if (posts.length === 0) {
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';

  posts.forEach((post, i) => {
    const accentClass = `post-card__accent--${i % 3}`;
    const date = post.created_at
      ? new Date(post.created_at.slice(0, 10) + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
      : '';

    const levelTag = post.level
      ? `<span class="tag tag--coral">${escapeHtml(post.level)}</span>` : '';
    const typeTag = post.content_type
      ? `<span class="tag tag--yellow">${escapeHtml(post.content_type)}</span>` : '';

    const card = document.createElement('div');
    card.className = 'post-card';
    card.innerHTML = `
      <div class="post-card__accent ${accentClass}"></div>
      <div class="post-card__body">
        <div class="post-card__meta">${levelTag}${typeTag}</div>
        <h3>${escapeHtml(post.title)}</h3>
        <div class="post-card__date">${date}</div>
      </div>
    `;
    card.addEventListener('click', () => openPost(post.id));
    grid.appendChild(card);
  });
}

// ── Search ────────────────────────────────────────────────────────────────

function _scorePost(post, terms) {
  // Weight: title > level/content_type > exam
  const fields = [
    { value: post.title        || '', weight: 3 },
    { value: post.level        || '', weight: 2 },
    { value: post.content_type || '', weight: 2 },
    { value: post.exam         || '', weight: 1 },
  ];
  let score = 0;
  for (const term of terms) {
    for (const { value, weight } of fields) {
      const v = value.toLowerCase();
      if (v === term)          score += weight * 2; // exact field match
      else if (v.includes(term)) score += weight;   // partial match
    }
  }
  return score;
}

function filterPosts() {
  const raw = document.getElementById('searchInput').value.trim().toLowerCase();
  const countEl = document.getElementById('resultCount');

  if (!raw) {
    renderPosts(allPosts);
    if (countEl) countEl.textContent = '';
    return;
  }

  const terms = raw.split(/\s+/).filter(Boolean);
  const results = allPosts
    .map(p => ({ post: p, score: _scorePost(p, terms) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .map(({ post }) => post);

  if (countEl) {
    countEl.textContent = results.length === 0
      ? 'No matches found'
      : `${results.length} result${results.length !== 1 ? 's' : ''}`;
  }

  renderPosts(results);
}

let _searchTimer;
document.getElementById('searchInput').addEventListener('input', () => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(filterPosts, 200);
});

document.getElementById('searchInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { clearTimeout(_searchTimer); filterPosts(); }
  if (e.key === 'Escape') {
    document.getElementById('searchInput').value = '';
    const countEl = document.getElementById('resultCount');
    if (countEl) countEl.textContent = '';
    renderPosts(allPosts);
  }
});

// ── Post modal ────────────────────────────────────────────────────────────

async function openPost(postId) {
  document.getElementById('modalTitle').textContent = 'Loading…';
  document.getElementById('modalMeta').textContent = '';
  document.getElementById('modalBody').innerHTML =
    '<div class="loading-state"><div class="spinner"></div></div>';
  document.getElementById('postModal').classList.add('open');

  const token = localStorage.getItem('hsk_token');

  if (!token) {
    document.getElementById('modalTitle').textContent = 'Subscribers only';
    document.getElementById('modalBody').innerHTML = `
      <div style="text-align:center;padding:2rem 0">
        <p style="margin-bottom:1.5rem">Log in or subscribe to read the full issue.</p>
        <a href="/login" class="btn btn--coral" style="margin-right:.75rem">Log In</a>
        <a href="/#subscribe" class="btn btn--ghost">Subscribe →</a>
      </div>`;
    return;
  }

  if (userStatus !== 'active') {
    document.getElementById('modalTitle').textContent = 'Subscribers only';
    document.getElementById('modalBody').innerHTML = `
      <div style="text-align:center;padding:2rem 0">
        <p style="margin-bottom:1.5rem">Subscribe to get full access to all issues.</p>
        <a href="/#subscribe" class="btn btn--coral">Subscribe →</a>
      </div>`;
    return;
  }

  // Active subscriber — fetch full post
  try {
    const res = await fetch(`${API}/api/posts/${postId}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (!res.ok) {
      document.getElementById('modalBody').textContent = 'Could not load this post.';
      return;
    }

    const post = await res.json();
    const date = post.created_at
      ? new Date(post.created_at.slice(0, 10) + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
      : '';

    document.getElementById('modalTitle').textContent = post.title || 'Untitled';
    document.getElementById('modalMeta').textContent =
      [post.level, post.exam, post.content_type, date].filter(Boolean).join(' · ');

    // Render content: prefer HTML, fall back to raw text
    const body = document.getElementById('modalBody');
    if (post.content_html) {
      body.innerHTML = post.content_html;
    } else if (post.content_raw) {
      body.innerHTML = '<pre style="white-space:pre-wrap">' + escapeHtml(post.content_raw) + '</pre>';
    } else {
      body.textContent = 'No content available.';
    }

  } catch (err) {
    document.getElementById('modalBody').textContent = 'Network error loading post.';
  }
}

function closePostModal() {
  document.getElementById('postModal').classList.remove('open');
}

// Close modal on backdrop click
document.getElementById('postModal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('postModal')) closePostModal();
});

// ── Sign out ──────────────────────────────────────────────────────────────

document.getElementById('signOutBtn').addEventListener('click', (e) => {
  e.preventDefault();
  localStorage.removeItem('hsk_token');
  window.location.href = '/login';
});

// ── Utilities ─────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Start ─────────────────────────────────────────────────────────────────
init();
