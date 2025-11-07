// 拦截toggleGameActions调用
if (window.pokerGame) {
    const originalToggleGameActions = window.pokerGame.toggleGameActions;
    
    window.pokerGame.toggleGameActions = function(showGameActions) {
        console.log('=== toggleGameActions 被调用 ===');
        console.log('参数:', showGameActions);
        console.log('调用堆栈:', new Error().stack);
        
        // 检查当前状态
        const gameActionSection = document.getElementById('game-action-section');
        const readySection = document.getElementById('ready-section');
        console.log('调用前 - 游戏操作区域显示状态:', gameActionSection?.style.display);
        console.log('调用前 - 准备区域显示状态:', readySection?.style.display);
        
        // 调用原始函数
        const result = originalToggleGameActions.call(this, showGameActions);
        
        // 检查调用后状态
        console.log('调用后 - 游戏操作区域显示状态:', gameActionSection?.style.display);
        console.log('调用后 - 准备区域显示状态:', readySection?.style.display);
        console.log('=== toggleGameActions 调用结束 ===');
        
        return result;
    };
}