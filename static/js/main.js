// 主JavaScript文件
class PokerApp {
    constructor() {
        this.currentUser = null;
        this.socket = null;
        this.init();
    }

    async init() {
        await this.checkAuth();
        this.setupEventListeners();
    }

    async checkAuth() {
        console.group('认证检查');
        
        try {
            // 1. 调试：检查所有cookie
            console.log('所有cookie:', document.cookie);
            
            // 2. 直接从cookie获取session_token（符合技术方案）
            let sessionToken = this.getCookie('session_token');
            console.log('首次从cookie获取sessionToken:', sessionToken);
            
            // 3. 如果cookie为空，等待一段时间后重试（给cookie设置时间）
            if (!sessionToken) {
                console.log('cookie为空，等待100ms后重试...');
                await new Promise(resolve => setTimeout(resolve, 100));
                sessionToken = this.getCookie('session_token');
                console.log('重试后从cookie获取sessionToken:', sessionToken);
            }
            
            // 4. 如果仍然为空，检查是否是重定向后的页面
            if (!sessionToken) {
                // 检查URL参数，看是否有认证错误
                const urlParams = new URLSearchParams(window.location.search);
                if (urlParams.has('auth_error')) {
                    console.warn('认证错误：cookie在重定向过程中丢失');
                    this.showToast('认证失败：请重新登录', 'error');
                    return false;
                }
                
                // 如果是房间页面但没有cookie，重定向到首页
                if (window.location.pathname === '/room') {
                    console.warn('房间页面缺少cookie，重定向到首页');
                    window.location.href = '/';
                    return false;
                }
                
                // 其他页面允许继续
                console.log('页面不需要认证');
                return true;
            }
            
            // 5. 验证token格式（UUID格式）
            const isValidToken = sessionToken && 
                               typeof sessionToken === 'string' && 
                               /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(sessionToken);
            
            if (!isValidToken) {
                console.error('无效的会话令牌格式:', sessionToken);
                const error = new Error('无效的会话令牌格式');
                error.token = sessionToken;
                throw error;
            }

            // 3. 调用API验证用户
            console.log('调用/api/user-info验证用户...');
            const startTime = performance.now();
            
            const response = await fetch('/api/user-info', {
                credentials: 'include'  // 自动包含cookie
            });
            
            const duration = (performance.now() - startTime).toFixed(2);
            console.log(`API调用完成，耗时${duration}ms`, response);

            if (response.ok) {
                this.currentUser = await response.json();
                console.log('认证成功，用户信息:', this.currentUser);
                this.updateUserInfo();
                return true;
            } else if (response.status === 401) {
                console.warn('认证失败，状态码401');
                
                // 清理无效的认证数据
                localStorage.removeItem('session_token');
                document.cookie = 'session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                
                this.showToast('认证失败: 无效的会话令牌', 'error');
                
                // 重定向到登录页
                if (window.location.pathname !== '/') {
                    setTimeout(() => {
                        window.location.href = '/?auth_error=1';
                    }, 1500);
                }
                return false;
            } else {
                const error = new Error(`HTTP错误! 状态码: ${response.status}`);
                error.response = response;
                throw error;
            }
        } catch (error) {
            console.error('认证检查失败:', error);
            
            let errorMessage = '认证检查失败';
            if (error.message.includes('Failed to fetch')) {
                errorMessage = '无法连接服务器';
            } else if (error.response) {
                errorMessage = `服务器错误: ${error.response.status}`;
            }
            
            this.showToast(`${errorMessage}: ${error.message}`, 'error');
            
            // 重定向到登录页
            if (window.location.pathname !== '/') {
                setTimeout(() => {
                    window.location.href = '/?auth_error=1';
                }, 2000);
            }
            
            return false;
        } finally {
            console.groupEnd();
        }
    }

    updateUserInfo() {
        const userInfoEl = document.querySelector('.user-info');
        if (userInfoEl && this.currentUser) {
            userInfoEl.innerHTML = `
                <span>欢迎, ${this.currentUser.nickname}</span>
                <span>筹码: ${this.currentUser.chips}</span>
            `;
        }
    }

    setupEventListeners() {
        // 全局事件监听器
        document.addEventListener('click', this.handleGlobalClick.bind(this));
        
        // 键盘快捷键
        document.addEventListener('keydown', this.handleKeyPress.bind(this));
    }

    handleGlobalClick(e) {
        // 处理模态框外部点击关闭
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (e.target === modal) {
                this.closeModal(modal);
            }
        });
    }

    handleKeyPress(e) {
        // ESC键关闭所有模态框
        if (e.key === 'Escape') {
            this.closeAllModals();
        }
    }

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    }

    closeModal(modal) {
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    }

    closeAllModals() {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => this.closeModal(modal));
    }

    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 10px;
            color: white;
            font-weight: bold;
            z-index: 10000;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
        `;

        const styleMap = {
            success: 'background: linear-gradient(135deg, #48bb78 0%, #38a169 100%)',
            error: 'background: linear-gradient(135deg, #f56565 0%, #e53e3e 100%)',
            warning: 'background: linear-gradient(135deg, #ed8936 0%, #dd6b20 100%)',
            info: 'background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%)'
        };

        toast.style.cssText += styleMap[type] || styleMap.info;

        document.body.appendChild(toast);

        // 显示动画
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        }, 10);

        // 自动隐藏
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    async apiCall(endpoint, options = {}) {
        try {
            const response = await fetch(endpoint, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (response.status === 401) {
                // 未授权，重定向到登录页
                window.location.href = '/';
                return null;
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API调用失败:', error);
            this.showToast(error.message, 'error');
            throw error;
        }
    }

    formatChips(amount) {
        if (amount >= 1000000) {
            return (amount / 1000000).toFixed(1) + 'M';
        } else if (amount >= 1000) {
            return (amount / 1000).toFixed(1) + 'K';
        }
        return amount.toString();
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    getCookie(name) {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith(name + '='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : null;
    }
}

// 初始化应用 - 确保DOM完全加载
document.addEventListener('DOMContentLoaded', function() {
    // 延迟执行以确保cookie已设置
    setTimeout(() => {
        window.pokerApp = new PokerApp();
    }, 100);
});

// 工具函数
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function getRandomColor() {
    const colors = [
        '#667eea', '#764ba2', '#f093fb', '#f5576c',
        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7',
        '#fa709a', '#fee140', '#a8edea', '#fed6e3'
    ];
    return colors[Math.floor(Math.random() * colors.length)];
}

// 本地存储工具
const storage = {
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.warn('本地存储失败:', error);
        }
    },

    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn('本地读取失败:', error);
            return defaultValue;
        }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.warn('本地删除失败:', error);
        }
    }
};