// Custom JS for Digital Event Organizer

document.addEventListener('DOMContentLoaded', () => {
    // Navbar scroll effect
    const navbar = document.querySelector('.glass-nav');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) {
                navbar.style.background = 'rgba(15, 12, 41, 0.95)';
                navbar.style.boxShadow = '0 5px 20px rgba(0,0,0,0.5)';
            } else {
                navbar.style.background = 'rgba(15, 12, 41, 0.7)';
                navbar.style.boxShadow = 'none';
            }
        });
    }

    // Handle alert dismissals with animation
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-20px)';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const savedTheme = localStorage.getItem('eventorg_theme');
        if (savedTheme === 'light') {
            document.body.classList.add('light-mode');
            themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        }

        themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('light-mode');
            const isLight = document.body.classList.contains('light-mode');
            localStorage.setItem('eventorg_theme', isLight ? 'light' : 'dark');
            themeToggle.innerHTML = isLight ? '<i class="fas fa-moon"></i>' : '<i class="fas fa-sun"></i>';
        });
    }

    // AI Chat Assistant
    const aiForm = document.getElementById('ai-form');
    if (aiForm) {
        aiForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = aiForm.querySelector('input');
            const msg = input.value.trim();
            if (!msg) return;
            
            const messagesDiv = document.getElementById('ai-messages');
            
            const userHtml = `<div class="bg-primary p-2 rounded-3 align-self-end text-white" style="max-width: 85%;"><p class="small mb-0">${escapeHtml(msg)}</p></div>`;
            messagesDiv.insertAdjacentHTML('beforeend', userHtml);
            input.value = '';
            
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            setTimeout(() => {
                let reply = "I can help you navigate to Explore Events, your Dashboard, or assist with booking seats.";
                const lower = msg.toLowerCase();
                if (lower.includes('book') || lower.includes('seat') || lower.includes('ticket')) {
                    reply = "To book tickets, explore events, select your preferred event and complete registration!";
                } else if (lower.includes('create') || lower.includes('admin') || lower.includes('organizer')) {
                    reply = "If you are an admin or organizer, visit your dashboard to manage and publish events.";
                } else if (lower.includes('hello') || lower.includes('hi')) {
                    reply = "Hello there! Welcome to EventOrg. Let me know if you need assistance.";
                }
                
                const aiHtml = `<div class="bg-white bg-opacity-10 p-2 rounded-3 align-self-start" style="max-width: 85%;"><p class="small mb-0">${escapeHtml(reply)}</p></div>`;
                messagesDiv.insertAdjacentHTML('beforeend', aiHtml);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }, 600);
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.innerText = text;
        return div.innerHTML;
    }
});
