// LevelSet — Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Flash message auto-dismiss
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.transition = 'opacity 0.5s ease';
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 500);
        }, 5000);
    });

    // Checkbox progress tracking for grant checklist
    const checklistForms = document.querySelectorAll('.checklist-form');
    checklistForms.forEach(form => {
        const checkboxes = form.querySelectorAll('input[type="checkbox"]');
        const progressFill = form.querySelector('.progress-fill');
        const progressText = form.querySelector('.progress-text');
        
        if (checkboxes.length > 0 && progressFill) {
            const updateProgress = () => {
                const checked = form.querySelectorAll('input[type="checkbox"]:checked').length;
                const total = checkboxes.length;
                const pct = Math.round((checked / total) * 100);
                if (progressFill) progressFill.style.width = pct + '%';
                if (progressText) progressText.textContent = `${checked} / ${total} (${pct}%)`;
            };
            
            checkboxes.forEach(cb => cb.addEventListener('change', updateProgress));
            updateProgress();
        }
    });

    // Form validation
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            let valid = true;
            const inputs = this.querySelectorAll('[required]');
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    input.classList.add('error');
                    valid = false;
                } else {
                    input.classList.remove('error');
                }
            });
            if (!valid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    });

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // PayPal button rendering
    if (typeof paypal !== 'undefined') {
        document.querySelectorAll('[data-paypal-button]').forEach(container => {
            const type = container.dataset.paypalButton;
            const reportId = container.dataset.reportId;
            const amount = container.dataset.amount || '49.00';
            
            if (type === 'buy_report' && reportId) {
                renderBuyReportButton(container, reportId, amount);
            } else if (type === 'subscribe') {
                renderSubscribeButton(container, amount);
            } else if (type === 'upgrade') {
                renderUpgradeButton(container, amount);
            }
        });
    }

    // User menu outside click handler
    const userMenus = document.querySelectorAll('.user-menu');
    document.addEventListener('click', function(e) {
        userMenus.forEach(menu => {
            if (!menu.contains(e.target)) {
                const dropdown = menu.querySelector('.dropdown-menu');
                if (dropdown) dropdown.classList.remove('show');
            }
        });
    });
    userMenus.forEach(menu => {
        menu.addEventListener('click', function(e) {
            const dropdown = this.querySelector('.dropdown-menu');
            if (dropdown) {
                dropdown.classList.toggle('show');
                e.stopPropagation();
            }
        });
    });
});

// ===== PayPal Button Functions =====

function renderBuyReportButton(container, reportId, amount) {
    paypal.Buttons({
        createOrder: function(data, actions) {
            return actions.order.create({
                purchase_units: [{
                    description: 'LevelSet Detailed Report',
                    amount: { value: amount }
                }]
            });
        },
        onApprove: function(data, actions) {
            return actions.order.capture().then(function(details) {
                // Send payment ID to server
                fetch('/pay/' + reportId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payment_id: details.id })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    }
                });
            });
        },
        onError: function(err) {
            console.error('PayPal Error:', err);
            alert('Payment processing failed. Please try again.');
        }
    }).render(container);
}

function renderSubscribeButton(container, amount) {
    paypal.Buttons({
        createOrder: function(data, actions) {
            return actions.order.create({
                purchase_units: [{
                    description: 'LevelSet Monthly Subscription',
                    amount: { value: amount }
                }]
            });
        },
        onApprove: function(data, actions) {
            return actions.order.capture().then(function(details) {
                fetch('/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payment_id: details.id })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    }
                });
            });
        },
        onError: function(err) {
            console.error('PayPal Error:', err);
            alert('Subscription processing failed. Please try again.');
        }
    }).render(container);
}

function renderUpgradeButton(container, amount) {
    paypal.Buttons({
        createOrder: function(data, actions) {
            return actions.order.create({
                purchase_units: [{
                    description: 'LevelSet Upgrade to Subscription',
                    amount: { value: amount }
                }]
            });
        },
        onApprove: function(data, actions) {
            return actions.order.capture().then(function(details) {
                fetch('/upgrade', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payment_id: details.id })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    }
                });
            });
        },
        onError: function(err) {
            console.error('PayPal Error:', err);
            alert('Upgrade processing failed. Please try again.');
        }
    }).render(container);
}

// ===== Utility: Free report claim =====
function claimFreeReport(reportId) {
    fetch('/free-report/' + reportId)
        .then(response => response.json())
        .then(data => {
            if (data.redirect) {
                window.location.href = data.redirect;
            } else if (data.error) {
                alert(data.error);
            }
        })
        .catch(err => {
            console.error('Error:', err);
            alert('Something went wrong. Please try again.');
        });
}
