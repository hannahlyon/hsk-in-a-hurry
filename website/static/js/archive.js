/* Archive page: auth check, post fetching, search, render */

const API = '';
let allPosts = [];

// ── Bootstrap ─────────────────────────────────────────────────────────────

async function init() {
  const token = localStorage.getItem('hsk_token');

  if (!token) {
    showGate('login');
    return;
  }

  try {
    const meRes = await fetch(`${API}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (meRes.status === 401) {
      localStorage.removeItem('hsk_token');
      showGate('login');
      return;
    }

    if (!meRes.ok) {
      showGate('error');
      return;
    }

    const user = await meRes.json();

    if (user.subscription_status !== 'active') {
      showGate('inactive');
      return;
    }

    // User is authenticated and paid — show archive
    document.getElementById('authGate').style.display = 'none';
    document.getElementById('archiveContent').style.display = 'block';
    document.getElementById('signOutBtn').style.display = 'inline-block';

    const greeting = document.getElementById('userGreeting');
    if (greeting) greeting.textContent = `Hi, ${user.name.split(' ')[0]}`;

    await loadPosts(token);

  } catch (err) {
    showGate('error');
  }
}

// ── Auth gate ─────────────────────────────────────────────────────────────

function showGate(reason) {
  document.getElementById('authGate').style.display = 'block';
  document.getElementById('archiveContent').style.display = 'none';

  const heading = document.getElementById('gateHeading');
  const message = document.getElementById('gateMessage');
  const loginBtn = document.getElementById('gateLoginBtn');
  const subBtn   = document.getElementById('gateSubscribeBtn');

  if (reason === 'login') {
    heading.textContent = 'Log in to read the archive';
    message.textContent = 'This page is for subscribers only. Please log in to continue.';
    loginBtn.style.display = 'inline-block';
    subBtn.style.display   = 'none';
  } else if (reason === 'inactive') {
    heading.textContent = 'No active subscription';
    message.textContent = 'Your account exists but doesn\'t have an active subscription yet. Subscribe to get full access.';
    loginBtn.style.display = 'none';
    subBtn.style.display   = 'inline-block';
  } else {
    heading.textContent = 'Something went wrong';
    message.textContent = 'We couldn\'t verify your session. Please try logging in again.';
    loginBtn.style.display = 'inline-block';
    subBtn.style.display   = 'none';
  }
}

// ── Posts ─────────────────────────────────────────────────────────────────

async function loadPosts(token) {
  try {
    const res = await fetch(`${API}/api/posts`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

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

function filterPosts() {
  const query = document.getElementById('searchInput').value.trim().toLowerCase();
  if (!query) {
    renderPosts(allPosts);
    return;
  }
  const filtered = allPosts.filter(p =>
    (p.title || '').toLowerCase().includes(query)
  );
  renderPosts(filtered);
}

document.getElementById('searchInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') filterPosts();
  if (e.key === 'Escape') {
    document.getElementById('searchInput').value = '';
    renderPosts(allPosts);
  }
});

// ── Post modal ────────────────────────────────────────────────────────────

async function openPost(postId) {
  const token = localStorage.getItem('hsk_token');
  if (!token) return;

  document.getElementById('modalTitle').textContent = 'Loading…';
  document.getElementById('modalMeta').textContent = '';
  document.getElementById('modalBody').innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
  document.getElementById('postModal').classList.add('open');

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
