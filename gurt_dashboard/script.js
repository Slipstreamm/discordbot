const API_ENDPOINT = '/discordapi/gurt/stats'; // Relative path to the API endpoint
const REFRESH_INTERVAL = 15000; // Refresh every 15 seconds (in milliseconds)

const lastUpdatedElement = document.getElementById('last-updated');
const runtimeStatsContainer = document.getElementById('runtime-stats');
const memoryStatsContainer = document.getElementById('memory-stats');
const apiStatsContainer = document.getElementById('api-stats');
const toolStatsContainer = document.getElementById('tool-stats');
const configStatsContainer = document.getElementById('config-stats');

function formatTimestamp(unixTimestamp) {
    if (!unixTimestamp || unixTimestamp === 0) return 'N/A';
    const date = new Date(unixTimestamp * 1000);
    return date.toLocaleString(); // Adjust format as needed
}

function createStatItem(label, value, isCode = false) {
    const item = document.createElement('div');
    item.classList.add('stat-item');

    const labelSpan = document.createElement('span');
    labelSpan.classList.add('stat-label');
    labelSpan.textContent = label + ':';
    item.appendChild(labelSpan);

    const valueSpan = document.createElement('span');
    valueSpan.classList.add('stat-value');
    if (isCode) {
        const code = document.createElement('code');
        code.textContent = value;
        valueSpan.appendChild(code);
    } else {
        valueSpan.textContent = value;
    }
    item.appendChild(valueSpan);
    return item;
}

function createListStatItem(label, items) {
    const item = document.createElement('div');
    item.classList.add('stat-item');

    const labelSpan = document.createElement('span');
    labelSpan.classList.add('stat-label');
    labelSpan.textContent = label + ':';
    item.appendChild(labelSpan);

    if (items && items.length > 0) {
        const list = document.createElement('ul');
        list.classList.add('stat-list');
        items.forEach(content => {
            const li = document.createElement('li');
            li.textContent = content;
            list.appendChild(li);
        });
        item.appendChild(list);
    } else {
        const valueSpan = document.createElement('span');
        valueSpan.classList.add('stat-value');
        valueSpan.textContent = 'None';
        item.appendChild(valueSpan);
    }
    return item;
}

function renderStats(stats) {
    // Clear previous stats
    runtimeStatsContainer.innerHTML = '<h2>Runtime</h2>';
    memoryStatsContainer.innerHTML = '<h2>Memory</h2>';
    apiStatsContainer.innerHTML = '<h2>API Stats</h2>';
    toolStatsContainer.innerHTML = '<h2>Tool Stats</h2>';
    configStatsContainer.innerHTML = '<h2>Config Overview</h2>';

    // Runtime Stats
    const runtime = stats.runtime || {};
    runtimeStatsContainer.appendChild(createStatItem('Current Mood', runtime.current_mood || 'N/A'));
    runtimeStatsContainer.appendChild(createStatItem('Mood Changed', formatTimestamp(runtime.last_mood_change_timestamp)));
    runtimeStatsContainer.appendChild(createStatItem('Background Task Running', runtime.background_task_running ? 'Yes' : 'No'));
    runtimeStatsContainer.appendChild(createStatItem('Needs JSON Reminder', runtime.needs_json_reminder ? 'Yes' : 'No'));
    runtimeStatsContainer.appendChild(createStatItem('Last Evolution', formatTimestamp(runtime.last_evolution_update_timestamp)));
    runtimeStatsContainer.appendChild(createStatItem('Active Topics Channels', runtime.active_topics_channels || 0));
    runtimeStatsContainer.appendChild(createStatItem('Conv History Channels', runtime.conversation_history_channels || 0));
    runtimeStatsContainer.appendChild(createStatItem('Thread History Threads', runtime.thread_history_threads || 0));
    runtimeStatsContainer.appendChild(createStatItem('User Relationships Pairs', runtime.user_relationships_pairs || 0));
    runtimeStatsContainer.appendChild(createStatItem('Cached Summaries', runtime.conversation_summaries_cached || 0));
    runtimeStatsContainer.appendChild(createStatItem('Cached Channel Topics', runtime.channel_topics_cached || 0));
    runtimeStatsContainer.appendChild(createStatItem('Global Msg Cache', runtime.message_cache_global_count || 0));
    runtimeStatsContainer.appendChild(createStatItem('Mention Msg Cache', runtime.message_cache_mentioned_count || 0));
    runtimeStatsContainer.appendChild(createStatItem('Active Convos', runtime.active_conversations_count || 0));
    runtimeStatsContainer.appendChild(createStatItem('Sentiment Channels', runtime.conversation_sentiment_channels || 0));
    runtimeStatsContainer.appendChild(createStatItem('Gurt Participation Topics', runtime.gurt_participation_topics_count || 0));
    runtimeStatsContainer.appendChild(createStatItem('Tracked Reactions', runtime.gurt_message_reactions_tracked || 0));

    // Memory Stats
    const memory = stats.memory || {};
    if (memory.error) {
        const errorItem = document.createElement('div');
        errorItem.classList.add('stat-item', 'error');
        errorItem.textContent = `Error: ${memory.error}`;
        memoryStatsContainer.appendChild(errorItem);
    } else {
        memoryStatsContainer.appendChild(createStatItem('User Facts', memory.user_facts_count || 0));
        memoryStatsContainer.appendChild(createStatItem('General Facts', memory.general_facts_count || 0));
        memoryStatsContainer.appendChild(createStatItem('Chroma Messages', memory.chromadb_message_collection_count || 'N/A'));
        memoryStatsContainer.appendChild(createStatItem('Chroma Facts', memory.chromadb_fact_collection_count || 'N/A'));

        const personality = memory.personality_traits || {};
        const pItems = Object.entries(personality).map(([k, v]) => `${k}: ${v}`);
        memoryStatsContainer.appendChild(createListStatItem('Personality Traits', pItems));

        const interests = memory.top_interests || [];
        const iItems = interests.map(([t, l]) => `${t}: ${l.toFixed(2)}`);
        memoryStatsContainer.appendChild(createListStatItem('Top Interests', iItems));
    }

    // API Stats
    const apiStats = stats.api_stats || {};
    if (Object.keys(apiStats).length === 0) {
        apiStatsContainer.appendChild(createStatItem('No API calls recorded yet.', ''));
    } else {
        for (const [model, data] of Object.entries(apiStats)) {
            const value = `Success: ${data.success || 0}, Failure: ${data.failure || 0}, Retries: ${data.retries || 0}, Avg Time: ${data.average_time_ms || 0} ms, Count: ${data.count || 0}`;
            apiStatsContainer.appendChild(createStatItem(model, value, true));
        }
    }


    // Tool Stats
    const toolStats = stats.tool_stats || {};
     if (Object.keys(toolStats).length === 0) {
        toolStatsContainer.appendChild(createStatItem('No tool calls recorded yet.', ''));
    } else {
        for (const [tool, data] of Object.entries(toolStats)) {
            const value = `Success: ${data.success || 0}, Failure: ${data.failure || 0}, Avg Time: ${data.average_time_ms || 0} ms, Count: ${data.count || 0}`;
            toolStatsContainer.appendChild(createStatItem(tool, value, true));
        }
    }

    // Config Stats
    const config = stats.config || {};
    configStatsContainer.appendChild(createStatItem('Default Model', config.default_model || 'N/A', true));
    configStatsContainer.appendChild(createStatItem('Fallback Model', config.fallback_model || 'N/A', true));
    configStatsContainer.appendChild(createStatItem('Semantic Model', config.semantic_model_name || 'N/A', true));
    configStatsContainer.appendChild(createStatItem('Max User Facts', config.max_user_facts || 'N/A'));
    configStatsContainer.appendChild(createStatItem('Max General Facts', config.max_general_facts || 'N/A'));
    configStatsContainer.appendChild(createStatItem('Context Window', config.context_window_size || 'N/A'));
    configStatsContainer.appendChild(createStatItem('API Key Set', config.api_key_set ? 'Yes' : 'No'));
    configStatsContainer.appendChild(createStatItem('Tavily Key Set', config.tavily_api_key_set ? 'Yes' : 'No'));
    configStatsContainer.appendChild(createStatItem('Piston URL Set', config.piston_api_url_set ? 'Yes' : 'No'));

}

async function fetchStats() {
    try {
        const response = await fetch(API_ENDPOINT);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const stats = await response.json();
        renderStats(stats);
        lastUpdatedElement.textContent = new Date().toLocaleTimeString();
    } catch (error) {
        console.error('Error fetching stats:', error);
        lastUpdatedElement.textContent = `Error fetching stats at ${new Date().toLocaleTimeString()}`;
        // Optionally display an error message in the UI
        runtimeStatsContainer.innerHTML = '<h2>Runtime</h2><p class="error">Could not load stats.</p>';
        memoryStatsContainer.innerHTML = '<h2>Memory</h2>';
        apiStatsContainer.innerHTML = '<h2>API Stats</h2>';
        toolStatsContainer.innerHTML = '<h2>Tool Stats</h2>';
        configStatsContainer.innerHTML = '<h2>Config Overview</h2>';
    }
}

// Initial fetch and set interval
fetchStats();
setInterval(fetchStats, REFRESH_INTERVAL);
