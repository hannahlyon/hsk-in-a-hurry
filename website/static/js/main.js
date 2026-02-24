/* Landing page JS: signup form → register → Stripe checkout redirect */

const API = '';  // same origin

function showError(msg) {
  const el = document.getElementById('signupError');
  el.textContent = msg;
  el.classList.add('visible');
}

function hideError() {
  const el = document.getElementById('signupError');
  el.classList.remove('visible');
}

document.getElementById('signupForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  hideError();

  const btn = document.getElementById('submitBtn');
  const name = document.getElementById('name').value.trim();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;

  if (password.length < 8) {
    showError('Password must be at least 8 characters.');
    return;
  }

  btn.textContent = 'Creating account…';
  btn.disabled = true;

  try {
    // Step 1: register
    const regRes = await fetch(`${API}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });

    if (!regRes.ok) {
      const err = await regRes.json();
      if (regRes.status === 409) {
        showError('That email is already registered. Please log in instead.');
      } else {
        showError(err.detail || 'Registration failed. Please try again.');
      }
      btn.textContent = 'Subscribe & Pay →';
      btn.disabled = false;
      return;
    }

    // Step 2: create Stripe checkout session
    btn.textContent = 'Redirecting to payment…';

    const checkoutRes = await fetch(`${API}/api/stripe/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });

    if (!checkoutRes.ok) {
      const err = await checkoutRes.json();
      showError(err.detail || 'Could not start checkout. Please try again.');
      btn.textContent = 'Subscribe & Pay →';
      btn.disabled = false;
      return;
    }

    const { url } = await checkoutRes.json();
    window.location.href = url;

  } catch (err) {
    showError('Network error. Please check your connection and try again.');
    btn.textContent = 'Subscribe & Pay →';
    btn.disabled = false;
  }
});

// Modal helpers
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

document.getElementById('privacyLink').addEventListener('click', (e) => {
  e.preventDefault();
  openModal('privacyModal');
});
document.getElementById('termsLink').addEventListener('click', (e) => {
  e.preventDefault();
  openModal('termsModal');
});

// Close modals on backdrop click
document.querySelectorAll('.modal-backdrop').forEach((bd) => {
  bd.addEventListener('click', (e) => {
    if (e.target === bd) bd.classList.remove('open');
  });
});
