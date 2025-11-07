// 临时调试脚本
console.log('=== 调试游戏操作区域问题 ===');

// 检查游戏操作区域当前状态
const gameActionSection = document.getElementById('game-action-section');
const readySection = document.getElementById('ready-section');

console.log('当前游戏操作区域状态:', {
    gameActionSection: !!gameActionSection,
    readySection: !!readySection,
    gameActionDisplay: gameActionSection?.style.display,
    readyDisplay: readySection?.style.display,
    gameActionVisible: gameActionSection ? gameActionSection.offsetParent !== null : 'N/A',
    readyVisible: readySection ? readySection.offsetParent !== null : 'N/A'
});

// 检查是否有CSS样式覆盖
if (gameActionSection) {
    const computedStyle = window.getComputedStyle(gameActionSection);
    console.log('游戏操作区域计算样式:', {
        display: computedStyle.display,
        visibility: computedStyle.visibility,
        opacity: computedStyle.opacity
    });
}

// 检查游戏状态
if (window.pokerGame) {
    console.log('游戏对象状态:', {
        gameState: !!window.pokerGame.gameState,
        stage: window.pokerGame.gameState?.stage,
        players: window.pokerGame.gameState?.players?.length
    });
}