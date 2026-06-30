document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('evaluation-form');
    const textarea = document.getElementById('expense-text');
    const submitBtn = document.getElementById('submit-btn');
    const spinner = submitBtn.querySelector('.spinner');
    const terminal = document.getElementById('terminal-output');
    
    // Quick Templates
    document.querySelectorAll('.btn-template').forEach(btn => {
        btn.addEventListener('click', () => {
            textarea.value = btn.getAttribute('data-text');
        });
    });

    // Form Submit handler
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = textarea.value.trim();
        if (!text) return;

        // Reset Dashboard & Terminal
        resetUI();
        
        // Show Loading State
        submitBtn.disabled = true;
        spinner.classList.remove('hidden');
        appendTerminalLine('System', 'Initiating multi-agent orchestration pipeline...', 'system-info');

        try {
            const response = await fetch('/api/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`Server returned ${response.status}: ${errText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                
                // Save last incomplete line back to buffer
                buffer = lines.pop();

                for (const line of lines) {
                    const cleaned = line.trim();
                    if (!cleaned.startsWith('data: ')) continue;
                    
                    try {
                        const jsonStr = cleaned.slice(6);
                        const eventData = JSON.parse(jsonStr);
                        processAgentEvent(eventData);
                    } catch (parseErr) {
                        // Suppress parse errors for malformed individual lines
                        console.error('Failed to parse line:', cleaned, parseErr);
                    }
                }
            }

            // Process whatever is left in buffer
            if (buffer.trim().startsWith('data: ')) {
                 try {
                     const eventData = JSON.parse(buffer.trim().slice(6));
                     processAgentEvent(eventData);
                 } catch (e) {}
            }

            appendTerminalLine('System', 'Pipeline execution finished successfully.', 'system-info');
        } catch (err) {
            console.error(err);
            appendTerminalLine('Error', err.message, 'error-info');
            showErrorVerdict(err.message);
        } finally {
            submitBtn.disabled = false;
            spinner.classList.add('hidden');
        }
    });

    // Reset Dashboard and Terminal UI
    function resetUI() {
        terminal.innerHTML = '';
        
        // Reset Verdict Card
        const verdictCard = document.getElementById('verdict-card');
        verdictCard.className = 'card glass-card status-card pending';
        document.getElementById('verdict-badge').textContent = 'Pending';
        document.getElementById('verdict-icon').textContent = '⚖️';
        document.getElementById('verdict-summary-text').textContent = 'No expense analyzed yet.';
        
        const violationsList = document.getElementById('violations-list');
        violationsList.innerHTML = '';
        violationsList.classList.add('hidden');

        // Reset Value Card
        document.getElementById('usd-value').textContent = '—';
        const approvalVal = document.getElementById('approval-value');
        approvalVal.textContent = '—';
        approvalVal.className = 'val-status';

        // Reset Insights Section
        const insightsSection = document.getElementById('insights-section');
        insightsSection.classList.add('disabled');
        document.getElementById('total-spend').textContent = '—';
        document.getElementById('violations-count').textContent = '—';
        document.getElementById('categories-list').innerHTML = '<p class="empty-state">No categories mapped.</p>';
        document.getElementById('anomalies-list').innerHTML = '<li class="empty-state">No anomalies flagged.</li>';
        document.getElementById('executive-summary').textContent = 'Waiting for analysis...';
    }

    // Append logs to the Terminal
    function appendTerminalLine(author, text, customClass = '') {
        // Remove empty state placeholder
        const placeholder = terminal.querySelector('.placeholder');
        if (placeholder) placeholder.remove();

        // Create label row
        if (author && author !== 'System' && author !== 'Error') {
            const labelLine = document.createElement('div');
            labelLine.className = 'terminal-line agent-label';
            labelLine.textContent = `[${author}]`;
            terminal.appendChild(labelLine);
        }

        // Create content row
        const contentLine = document.createElement('div');
        contentLine.className = `terminal-line ${customClass}`;
        contentLine.textContent = text;
        terminal.appendChild(contentLine);
        
        // Scroll terminal to bottom
        terminal.scrollTop = terminal.scrollHeight;
    }

    // Process a streamed Agent Event
    function processAgentEvent(event) {
        const author = event.author;
        const errorMsg = event.error_message;
        
        // Handle stream-level error response
        if (errorMsg) {
             appendTerminalLine('Error', `Agent Execution Failed: ${errorMsg}`, 'error-info');
             showErrorVerdict(errorMsg);
             return;
        }

        const content = event.content;
        if (!content || !content.parts || content.parts.length === 0) return;

        const rawText = content.parts[0].text;
        if (!rawText) return;

        // Log agent thinking output
        appendTerminalLine(author, rawText);

        // Try to extract and parse JSON payload
        const jsonPayload = extractJSON(rawText);
        if (!jsonPayload) return;

        // Route payload to correct dashboard component
        if (author === 'intake_agent') {
            updateIntakeDashboard(jsonPayload);
        } else if (author === 'policy_agent') {
            updatePolicyDashboard(jsonPayload);
        } else if (author === 'insights_agent') {
            updateInsightsDashboard(jsonPayload);
        }
    }

    // Extract JSON string from markdown content if present
    function extractJSON(text) {
        let cleanText = text.trim();
        // Remove markdown wrappers if present
        if (cleanText.startsWith('```json')) {
            cleanText = cleanText.slice(7);
        } else if (cleanText.startsWith('```')) {
            cleanText = cleanText.slice(3);
        }
        if (cleanText.endsWith('```')) {
            cleanText = cleanText.slice(0, -3);
        }
        cleanText = cleanText.trim();
        
        try {
            return JSON.parse(cleanText);
        } catch (e) {
            // Text is not JSON, return null
            return null;
        }
    }

    // Display Error in the Verdict Card
    function showErrorVerdict(msg) {
        const verdictCard = document.getElementById('verdict-card');
        verdictCard.className = 'card glass-card status-card non-compliant';
        document.getElementById('verdict-badge').textContent = 'Error';
        document.getElementById('verdict-icon').textContent = '❌';
        document.getElementById('verdict-summary-text').textContent = `Execution failed: ${msg}`;
    }

    // Update Dashboard: Intake Results
    function updateIntakeDashboard(data) {
        const amount = data.amount;
        const currency = data.currency || 'USD';
        document.getElementById('usd-value').textContent = `${amount.toFixed(2)} ${currency}`;
        appendTerminalLine('System', `Structured expense details successfully extracted.`, 'system-info');
    }

    // Update Dashboard: Policy compliance Results
    function updatePolicyDashboard(data) {
        const verdictCard = document.getElementById('verdict-card');
        const badge = document.getElementById('verdict-badge');
        const icon = document.getElementById('verdict-icon');
        const summary = document.getElementById('verdict-summary-text');
        const list = document.getElementById('violations-list');
        
        list.innerHTML = '';
        
        const isCompliant = data.is_compliant;
        if (isCompliant) {
            verdictCard.className = 'card glass-card status-card compliant';
            badge.textContent = 'Compliant';
            icon.textContent = '✅';
            summary.textContent = 'This expense complies with all category policy limits.';
            list.classList.add('hidden');
        } else {
            verdictCard.className = 'card glass-card status-card non-compliant';
            badge.textContent = 'Violation';
            icon.textContent = '⚠️';
            summary.textContent = 'Policy violation(s) identified:';
            
            if (data.violations && data.violations.length > 0) {
                data.violations.forEach(v => {
                    const li = document.createElement('li');
                    li.textContent = v;
                    list.appendChild(li);
                });
                list.classList.remove('hidden');
            } else {
                list.classList.add('hidden');
            }
        }

        // Set USD value normalized
        if (data.usd_amount !== undefined) {
             document.getElementById('usd-value').textContent = `$${data.usd_amount.toFixed(2)} USD`;
        }

        // Set manager approval status
        const approvalVal = document.getElementById('approval-value');
        if (data.needs_approval) {
            approvalVal.textContent = 'Required';
            approvalVal.className = 'val-status yes';
        } else {
            approvalVal.textContent = 'Not Required';
            approvalVal.className = 'val-status no';
        }
        
        appendTerminalLine('System', `Policy compliance checks complete. Verdict: ${isCompliant ? 'COMPLIANT' : 'VIOLATION'}.`, 'system-info');
    }

    // Update Dashboard: Aggregated Analytics Insights
    function updateInsightsDashboard(data) {
        const section = document.getElementById('insights-section');
        section.classList.remove('disabled');

        // Set basic insights
        if (data.total_spend !== undefined) {
             document.getElementById('total-spend').textContent = `$${data.total_spend.toFixed(2)}`;
        }
        if (data.violations_count !== undefined) {
             document.getElementById('violations-count').textContent = data.violations_count;
        }

        // Categories List
        const catsList = document.getElementById('categories-list');
        catsList.innerHTML = '';
        const cats = data.spend_by_category || {};
        const catKeys = Object.keys(cats);
        
        if (catKeys.length > 0) {
            const maxVal = Math.max(...Object.values(cats), 1.0);
            catKeys.forEach(name => {
                const val = cats[name];
                const pct = (val / maxVal) * 100;
                
                const row = document.createElement('div');
                row.className = 'category-row';
                row.innerHTML = `
                    <div class="category-labels">
                        <span class="category-name">${name}</span>
                        <span class="category-val">$${val.toFixed(2)}</span>
                    </div>
                    <div class="category-bar-wrapper">
                        <div class="category-bar" style="width: 0%"></div>
                    </div>
                `;
                catsList.appendChild(row);
                
                // Trigger width animation on next repaint
                setTimeout(() => {
                    row.querySelector('.category-bar').style.width = `${pct}%`;
                }, 50);
            });
        } else {
            catsList.innerHTML = '<p class="empty-state">No categories mapped.</p>';
        }

        // Anomalies List
        const anomList = document.getElementById('anomalies-list');
        anomList.innerHTML = '';
        if (data.anomalies && data.anomalies.length > 0) {
            data.anomalies.forEach(anom => {
                const li = document.createElement('li');
                li.textContent = anom;
                anomList.appendChild(li);
            });
        } else {
            anomList.innerHTML = '<li class="empty-state">No anomalies flagged.</li>';
        }

        // Executive Summary
        const execSummary = document.getElementById('executive-summary');
        if (data.summary) {
            execSummary.textContent = data.summary;
        } else {
            execSummary.textContent = 'No summary provided.';
        }

        appendTerminalLine('System', 'Aggregated portfolio insights generated.', 'system-info');
    }
});
