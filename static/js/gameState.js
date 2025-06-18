/**
 * Game State Management Module
 * Handles all game state, scoring, and UI updates for the quiz game
 */

const GameState = (function() {
    // Private variables
    let currentCycle = 0;
    let currentTossupPoints = 0;
    let currentTossupTeam = 0;
    let scorecard = {
        team1: { score: 0, players: [] },
        team2: { score: 0, players: [] },
        cycles: []
    };
    let activePlayers = {
        team1: [],
        team2: []
    };
    let questions = [];
    let bonuses = [];

    // Initialize the game
    function init() {
        // Initialize from template data
        const config = window.GAME_CONFIG || {};
        
        // Initialize active players
        activePlayers.team1 = Array(config.PLAYERS_TEAM1?.length || 0).fill(true);
        activePlayers.team2 = Array(config.PLAYERS_TEAM2?.length || 0).fill(true);
        
        // Initialize scorecard
        initializeScorecard();
        
        // Load questions if available
        if (config.QUESTIONS) {
            questions = config.QUESTIONS;
        }
        
        // Load bonuses if available
        if (config.BONUSES) {
            bonuses = config.BONUSES;
        }
        
        // Load saved progress if available
        loadFromLocalStorage();
        
        // Update UI
        updateUI();
    }

    /**
     * Initialize the scorecard with empty cycles
     */
    function initializeScorecard() {
        // Initialize player scores
        scorecard.team1.players = Array(activePlayers.team1.length).fill(0);
        scorecard.team2.players = Array(activePlayers.team2.length).fill(0);
        
        // Initialize cycles
        scorecard.cycles = Array(20).fill().map(() => ({
            team1: { tossup: 0, bonus: 0, players: Array(activePlayers.team1.length).fill(0) },
            team2: { tossup: 0, bonus: 0, players: Array(activePlayers.team2.length).fill(0) }
        }));
    }

    /**
     * Toggle player active status
     * @param {number} team - Team number (1 or 2)
     * @param {number} playerIndex - Index of the player in their team
     */
    function togglePlayer(team, playerIndex) {
        if (team !== 1 && team !== 2) return;
        
        const teamKey = `team${team}`;
        if (playerIndex >= 0 && playerIndex < activePlayers[teamKey].length) {
            activePlayers[teamKey][playerIndex] = !activePlayers[teamKey][playerIndex];
            updateUI();
            saveToLocalStorage();
        }
    }

    /**
     * Set points for a player in the current cycle
     * @param {number} points - Points to award
     * @param {number} team - Team number (1 or 2)
     * @param {number} playerIndex - Index of the player in their team
     */
    function setPlayerScore(points, team, playerIndex) {
        if (team !== 1 && team !== 2) return;
        
        const teamKey = `team${team}`;
        const cycle = scorecard.cycles[currentCycle];
        
        // Update cycle score
        cycle[teamKey].players[playerIndex] = points;
        
        // Update player's total score
        scorecard[teamKey].players[playerIndex] = scorecard.cycles.reduce((sum, c) => 
            sum + c[teamKey].players[playerIndex], 0
        );
        
        // Update team's total score
        scorecard[teamKey].score = scorecard[teamKey].players.reduce((a, b) => a + b, 0);
        
        updateUI();
        saveToLocalStorage();
    }

    /**
     * Move to the next cycle
     */
    function nextCycle() {
        if (currentCycle < scorecard.cycles.length - 1) {
            currentCycle++;
            currentTossupPoints = 0;
            currentTossupTeam = 0;
            updateUI();
            saveToLocalStorage();
        }
    }

    /**
     * Move to the previous cycle
     */
    function prevCycle() {
        if (currentCycle > 0) {
            currentCycle--;
            updateUI();
        }
    }

    /**
     * Save game state to localStorage
     */
    function saveToLocalStorage() {
        const gameState = {
            currentCycle,
            currentTossupPoints,
            currentTossupTeam,
            scorecard,
            activePlayers,
            lastSaved: new Date().toISOString()
        };
        
        try {
            localStorage.setItem(`quizGameState_${window.GAME_CONFIG?.GAME_ID}`, JSON.stringify(gameState));
            return true;
        } catch (e) {
            console.error('Failed to save game state:', e);
            return false;
        }
    }

    /**
     * Load game state from localStorage
     */
    function loadFromLocalStorage() {
        try {
            const savedState = localStorage.getItem(`quizGameState_${window.GAME_CONFIG?.GAME_ID}`);
            if (!savedState) return false;
            
            const state = JSON.parse(savedState);
            
            // Validate loaded state
            if (state.scorecard && state.scorecard.cycles) {
                currentCycle = state.currentCycle || 0;
                currentTossupPoints = state.currentTossupPoints || 0;
                currentTossupTeam = state.currentTossupTeam || 0;
                scorecard = state.scorecard;
                activePlayers = state.activePlayers || activePlayers;
                return true;
            }
        } catch (e) {
            console.error('Failed to load game state:', e);
        }
        return false;
    }

    /**
     * Update the UI to reflect current game state
     */
    function updateUI() {
        // Update cycle display
        const cycleDisplay = document.getElementById('currentCycleDisplay');
        if (cycleDisplay) {
            cycleDisplay.textContent = currentCycle + 1;
        }
        
        // Update progress bar
        const progressBar = document.getElementById('progressBar');
        if (progressBar) {
            const progress = ((currentCycle + 1) / scorecard.cycles.length) * 100;
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
        }
        
        // Update scores
        updateScores();
        
        // Update player selection UI
        updatePlayerSelectionUI();
    }

    /**
     * Update the scores display
     */
    function updateScores() {
        // Update team 1 score
        const team1Score = document.getElementById('team1Score');
        if (team1Score) {
            team1Score.textContent = scorecard.team1.score;
        }
        
        // Update team 2 score
        const team2Score = document.getElementById('team2Score');
        if (team2Score) {
            team2Score.textContent = scorecard.team2.score;
        }
    }

    /**
     * Update the player selection UI
     */
    function updatePlayerSelectionUI() {
        // Update team 1 players
        const team1Container = document.getElementById('team1Players');
        if (team1Container) {
            const players = window.GAME_CONFIG?.PLAYERS_TEAM1 || [];
            team1Container.innerHTML = players.map((player, index) => `
                <div class="form-check">
                    <input class="form-check-input player-checkbox" type="checkbox" 
                           id="player1_${index}" data-team="1" data-player="${index}" 
                           ${activePlayers.team1[index] ? 'checked' : ''}>
                    <label class="form-check-label" for="player1_${index}">
                        ${player}
                    </label>
                </div>
            `).join('');
        }
        
        // Update team 2 players
        const team2Container = document.getElementById('team2Players');
        if (team2Container) {
            const players = window.GAME_CONFIG?.PLAYERS_TEAM2 || [];
            team2Container.innerHTML = players.map((player, index) => `
                <div class="form-check">
                    <input class="form-check-input player-checkbox" type="checkbox" 
                           id="player2_${index}" data-team="2" data-player="${index}"
                           ${activePlayers.team2[index] ? 'checked' : ''}>
                    <label class="form-check-label" for="player2_${index}">
                        ${player}
                    </label>
                </div>
            `).join('');
        }
        
        // Re-attach event listeners
        setupEventListeners();
    }

    /**
     * Set up event listeners
     */
    function setupEventListeners() {
        // Player checkbox toggles
        document.querySelectorAll('.player-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const team = parseInt(e.target.dataset.team);
                const playerIndex = parseInt(e.target.dataset.player);
                togglePlayer(team, playerIndex);
            });
        });
        
        // Point buttons
        document.querySelectorAll('[data-points]').forEach(button => {
            button.addEventListener('click', (e) => {
                const points = parseInt(e.target.dataset.points);
                // Handle point assignment logic here
            });
        });
        
        // Navigation buttons
        const prevBtn = document.getElementById('prevCycle');
        if (prevBtn) {
            prevBtn.addEventListener('click', prevCycle);
        }
        
        const nextBtn = document.getElementById('nextCycle');
        if (nextBtn) {
            nextBtn.addEventListener('click', nextCycle);
        }
        
        // Save progress button
        const saveBtn = document.getElementById('saveProgressBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveToLocalStorage);
        }
        
        // Submit game button
        const submitBtn = document.getElementById('submitGameBtn');
        if (submitBtn) {
            submitBtn.addEventListener('click', submitGame);
        }
    }
    
    /**
     * Submit the game
     */
    function submitGame() {
        // Validate game completion
        if (currentCycle < scorecard.cycles.length - 1) {
            if (!confirm('You have not completed all cycles. Submit anyway?')) {
                return;
            }
        }
        
        // Prepare submission data
        const submission = {
            gameId: window.GAME_CONFIG?.GAME_ID,
            scorecard,
            completed: currentCycle >= scorecard.cycles.length - 1,
            submittedAt: new Date().toISOString()
        };
        
        // Submit via fetch API
        fetch('/submit-game', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify(submission)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Game submitted successfully!');
                // Clear saved state on successful submission
                localStorage.removeItem(`quizGameState_${window.GAME_CONFIG?.GAME_ID}`);
                // Optionally redirect
                if (data.redirect) {
                    window.location.href = data.redirect;
                }
            } else {
                throw new Error(data.error || 'Failed to submit game');
            }
        })
        .catch(error => {
            console.error('Error submitting game:', error);
            alert(`Failed to submit game: ${error.message}`);
        });
    }

    // Public API
    return {
        init,
        nextCycle,
        prevCycle,
        togglePlayer,
        setPlayerScore,
        saveToLocalStorage,
        loadFromLocalStorage,
        submitGame,
        getCurrentCycle: () => currentCycle,
        getScorecard: () => JSON.parse(JSON.stringify(scorecard)),
        getActivePlayers: (team) => [...(activePlayers[`team${team}`] || [])]
    };
})();

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize game state
    GameState.init();
    
    // Set up keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Number keys for points (0-9, - for neg)
        const pointKeys = {
            '1': 10, '2': 15, '3': 0, '4': 0, '5': 0,
            '6': 0, '7': 0, '8': 0, '9': 0, '0': 0, '-': -5
        };
        
        const points = pointKeys[e.key];
        if (points !== undefined) {
            const button = document.querySelector(`[data-points="${points}"]`);
            if (button) button.click();
        }
        // Left/right arrow keys for navigation
        else if (e.key === 'ArrowLeft') {
            const prevBtn = document.getElementById('prevCycle');
            if (prevBtn) prevBtn.click();
        }
        else if (e.key === 'ArrowRight') {
            const nextBtn = document.getElementById('nextCycle');
            if (nextBtn) nextBtn.click();
        }
    });
});
