// Library Management System – Premium JavaScript
// Glassmorphism UI Interactions

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle for mobile
    const sidebar = document.getElementById('appSidebar');
    const openBtn = document.getElementById('sidebarOpen');
    const closeBtn = document.getElementById('sidebarClose');

    // Create overlay
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay && sidebar) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }

    if (openBtn) {
        openBtn.addEventListener('click', function() {
            sidebar.classList.add('show');
            if (overlay) overlay.classList.add('show');
        });
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('show');
        if (overlay) overlay.classList.remove('show');
    }

    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (overlay) overlay.addEventListener('click', closeSidebar);

    // Auto-dismiss flash messages after 5 seconds with smooth fade
    document.querySelectorAll('.alert-dismissible').forEach(function(alert) {
        setTimeout(function() {
            alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-8px)';
            setTimeout(function() {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }, 400);
        }, 5000);
    });

    // Notification badge polling (every 60 seconds)
    if (document.querySelector('[data-bs-toggle="dropdown"] .badge')) {
        setInterval(function() {
            fetch('/api/notification-count')
                .then(r => r.json())
                .then(data => {
                    document.querySelectorAll('.badge.bg-danger').forEach(function(badge) {
                        if (badge.closest('[data-bs-toggle="dropdown"]')) {
                            if (data.count > 0) {
                                badge.textContent = data.count;
                                badge.style.display = '';
                            } else {
                                badge.style.display = 'none';
                            }
                        }
                    });
                })
                .catch(() => {});
        }, 60000);
    }

    // Confirm delete forms
    document.querySelectorAll('form[data-confirm]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!confirm(form.dataset.confirm || 'Are you sure?')) {
                e.preventDefault();
            }
        });
    });

    // Staggered entrance animations for card rows
    document.querySelectorAll('.row.g-3, .row.g-4').forEach(function(row) {
        const cards = row.querySelectorAll('.card');
        cards.forEach(function(card, index) {
            card.style.animationDelay = (index * 0.06) + 's';
        });
    });

    // Smooth hover tilt for stat cards
    document.querySelectorAll('.stat-card').forEach(function(card) {
        card.addEventListener('mousemove', function(e) {
            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            card.style.transform = `perspective(600px) rotateY(${x * 4}deg) rotateX(${-y * 4}deg) translateY(-2px)`;
        });
        card.addEventListener('mouseleave', function() {
            card.style.transform = 'perspective(600px) rotateY(0deg) rotateX(0deg) translateY(0)';
            card.style.transition = 'transform 0.4s ease';
        });
        card.addEventListener('mouseenter', function() {
            card.style.transition = 'transform 0.1s ease';
        });
    });

    // Ripple effect on buttons
    document.querySelectorAll('.btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            const rect = btn.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            ripple.style.cssText = `
                position:absolute;
                width:${size}px;height:${size}px;
                left:${e.clientX - rect.left - size/2}px;
                top:${e.clientY - rect.top - size/2}px;
                background:rgba(255,255,255,0.3);
                border-radius:50%;
                transform:scale(0);
                animation:rippleAnim 0.6s ease-out;
                pointer-events:none;
            `;
            btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });

    // Print support
    window.printReport = function() {
        window.print();
    };
});

// Inject ripple keyframes
const style = document.createElement('style');
style.textContent = `
    @keyframes rippleAnim {
        to { transform: scale(4); opacity: 0; }
    }
`;
document.head.appendChild(style);
