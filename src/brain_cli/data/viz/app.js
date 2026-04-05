(function () {
    'use strict';

    var COLORS = {
        company:       '#4fc3f7',
        project:       '#ba68c8',
        person:        '#fff176',
        instance:      '#4dd0e1',
        product:       '#81c784',
        goal:          '#aed581',
        task:          '#dce775',
        decision:      '#ffb74d',
        blocker:       '#e57373',
        event:         '#90a4ae',
        status_change: '#90a4ae',
        observation:   '#90a4ae',
    };

    var SIZES = {
        company: 80, project: 70,
        person: 48, instance: 40,
        product: 36,
        goal: 26, decision: 24, blocker: 24,
        task: 20,
        event: 16, status_change: 16, observation: 16,
    };

    // Hub types -- these get positioned first as cluster centers
    var HUB_TYPES = { company: true, project: true };

    var cy, selectedNode;

    // Custom layout: hubs in a ring, children clustered around their hub
    function hubClusterLayout() {
        var nodes = cy.nodes(':visible');
        var edges = cy.edges(':visible');

        // 1. Find hub nodes
        var hubs = nodes.filter(function (n) { return HUB_TYPES[n.data('type')]; });
        var others = nodes.filter(function (n) { return !HUB_TYPES[n.data('type')]; });

        // 2. Position hubs in a ring -- use large radius so clusters don't overlap
        var cx = cy.width() / 2;
        var cy_ = cy.height() / 2;
        var hubRadius = Math.max(cx, cy_) * 1.2;
        if (hubs.length <= 4) hubRadius = Math.max(cx, cy_) * 0.8;

        var hubPositions = {};
        hubs.forEach(function (hub, i) {
            var angle = (2 * Math.PI * i / hubs.length) - Math.PI / 2;
            var x = cx + hubRadius * Math.cos(angle);
            var y = cy_ + hubRadius * Math.sin(angle);
            hubPositions[hub.id()] = { x: x, y: y };
            hub.position({ x: x, y: y });
        });

        // 3. For each non-hub node, find which hub(s) it connects to
        others.forEach(function (node) {
            var connected = node.neighborhood('node').filter(function (n) { return HUB_TYPES[n.data('type')]; });

            if (connected.length === 0) {
                // No hub connection -- check if connected to something that IS connected to a hub
                var secondHop = node.neighborhood('node');
                secondHop.forEach(function (neighbor) {
                    var neighborHubs = neighbor.neighborhood('node').filter(function (n) { return HUB_TYPES[n.data('type')]; });
                    connected = connected.union(neighborHubs);
                });
            }

            if (connected.length === 0) {
                // Truly orphan -- place near center
                node.position({ x: cx + (Math.random() - 0.5) * 200, y: cy_ + (Math.random() - 0.5) * 200 });
                return;
            }

            // Average position of connected hubs
            var ax = 0, ay = 0;
            connected.forEach(function (h) {
                var p = hubPositions[h.id()] || h.position();
                ax += p.x;
                ay += p.y;
            });
            ax /= connected.length;
            ay /= connected.length;

            // If connected to exactly one hub, cluster tightly around it
            // If connected to multiple, position between them (closer to center)
            var spread;
            var sz = SIZES[node.data('type')] || 18;
            if (connected.length === 1) {
                spread = 120 + (100 - sz);
            } else {
                spread = 60;
            }

            // Offset by node type layer: people closer, goals/blockers further
            var layerOffset = 0;
            var type = node.data('type');
            if (type === 'person') layerOffset = 0.4;
            else if (type === 'instance') layerOffset = 0.5;
            else if (type === 'product') layerOffset = 0.6;
            else if (type === 'goal' || type === 'blocker' || type === 'decision') layerOffset = 0.8;
            else layerOffset = 1.0;

            // Pull toward center proportional to how many hubs they connect to
            var pullToCenter = connected.length > 1 ? 0.3 : 0;
            ax = ax + (cx - ax) * pullToCenter;
            ay = ay + (cy_ - ay) * pullToCenter;

            // Random angle for spread
            var angle = Math.random() * 2 * Math.PI;
            var dist = spread * layerOffset + Math.random() * spread * 0.5;

            node.position({
                x: ax + dist * Math.cos(angle),
                y: ay + dist * Math.sin(angle),
            });
        });

        // 4. Run a quick force simulation to resolve overlaps
        for (var iter = 0; iter < 120; iter++) {
            nodes.forEach(function (a) {
                nodes.forEach(function (b) {
                    if (a.id() >= b.id()) return;
                    var ap = a.position(), bp = b.position();
                    var dx = bp.x - ap.x, dy = bp.y - ap.y;
                    var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    var minDist = ((SIZES[a.data('type')] || 18) + (SIZES[b.data('type')] || 18)) * 0.8 + 40;
                    if (dist < minDist) {
                        var push = (minDist - dist) / 2;
                        var nx = (dx / dist) * push, ny = (dy / dist) * push;
                        // Don't push hubs
                        if (!HUB_TYPES[a.data('type')]) a.position({ x: ap.x - nx, y: ap.y - ny });
                        if (!HUB_TYPES[b.data('type')]) b.position({ x: bp.x + nx, y: bp.y + ny });
                    }
                });
            });
        }
    }

    function stylesheet() {
        var s = [
            { selector: 'node', style: {
                'shape': 'ellipse',
                'label': 'data(title)',
                'text-wrap': 'wrap',
                'text-max-width': '110px',
                'font-size': '9px',
                'font-weight': '500',
                'color': '#e0e0e0',
                'text-outline-color': '#2d2d2d',
                'text-outline-width': 2,
                'text-valign': 'center',
                'text-halign': 'center',
                'width': 20, 'height': 20,
                'background-color': '#666',
                'background-opacity': 0.85,
                'border-width': 0,
            }},
            { selector: 'node.dimmed', style: { 'opacity': 0.08 }},
            { selector: 'edge.dimmed', style: { 'opacity': 0.02 }},
            { selector: 'node.highlighted', style: { 'border-width': 3, 'border-color': '#fff' }},
            { selector: 'node.sel', style: { 'border-width': 2, 'border-color': '#fff' }},
            // Edges -- dashed lines, label ON the line
            { selector: 'edge', style: {
                'curve-style': 'bezier',
                'target-arrow-shape': 'triangle',
                'label': 'data(verb)',
                'font-size': '7px',
                'color': '#ccc',
                'text-rotation': 'autorotate',
                'text-background-color': '#2d2d2d',
                'text-background-opacity': 1,
                'text-background-padding': '3px',
                'text-background-shape': 'roundrectangle',
                'line-style': 'dashed',
                'line-dash-pattern': [6, 4],
                'line-color': '#888',
                'target-arrow-color': '#888',
                'width': 1,
                'arrow-scale': 0.7,
                'opacity': 0.6,
            }},
            { selector: 'edge[!active]', style: { 'opacity': 0.15 }},
            // Status
            { selector: 'node[status = "blocked"]', style: { 'border-width': 2, 'border-style': 'dashed', 'border-color': '#e57373' }},
            { selector: 'node[status = "stalled"]', style: { 'border-width': 2, 'border-style': 'dashed', 'border-color': '#ffb74d' }},
            { selector: 'node[status = "archived"]', style: { 'opacity': 0.25 }},
            { selector: 'node[staleness_level = "warning"]', style: { 'opacity': 0.5 }},
            { selector: 'node[staleness_level = "critical"]', style: { 'opacity': 0.2 }},
        ];

        for (var type in COLORS) {
            var sz = SIZES[type] || 18;
            var labelPos = sz >= 40 ? 'center' : 'bottom';
            var fontSize = sz >= 70 ? '12px' : (sz >= 40 ? '9px' : '8px');
            var labelMargin = labelPos === 'bottom' ? 5 : 0;

            s.push({ selector: 'node[type = "' + type + '"]', style: {
                'background-color': COLORS[type],
                'width': sz, 'height': sz,
                'font-size': fontSize,
                'text-valign': labelPos,
                'text-margin-y': labelMargin,
            }});
        }
        return s;
    }

    // ---- Markdown ----
    function md(text) {
        if (!text) return '';
        return text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/^### (.+)$/gm, '<h5>$1</h5>')
            .replace(/^## (.+)$/gm, '<h4>$1</h4>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/~~(.+?)~~/g, '<del>$1</del>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>[\s\S]*?<\/li>)/g, function (m) { return '<ul>' + m + '</ul>'; })
            .replace(/<\/ul>\s*<ul>/g, '')
            .replace(/\n{2,}/g, '<br>')
            .replace(/\n/g, '<br>');
    }

    // ---- Panel ----
    function openPanel(html) {
        document.getElementById('panel-body').innerHTML = html;
        document.getElementById('panel').classList.add('open');
    }

    function closePanel() {
        document.getElementById('panel').classList.remove('open');
        if (cy) cy.nodes().removeClass('sel');
    }

    function showNode(node) {
        cy.nodes().removeClass('sel');
        node.addClass('sel');

        var d = node.data();
        var color = COLORS[d.type] || '#666';
        var bc = 'b-' + (d.status || 'active');

        var h = '<div class="p-header">';
        h += '<div class="p-type"><span class="dot" style="background:' + color + '"></span>' + (d.type || '') + '</div>';
        h += '<div class="p-title">' + (d.title || d.id) + '</div>';
        h += '<div class="p-meta">';
        h += '<span class="badge ' + bc + '">' + (d.status || '?') + '</span>';
        if (d.freshness_days != null) h += '<span class="p-fresh">' + d.freshness_days + 'd old</span>';
        h += '<span class="p-id">' + d.id + '</span>';
        h += '</div></div>';

        if (d.content) {
            h += '<div class="p-section"><div class="p-label">Details</div><div class="p-md">' + md(d.content) + '</div></div>';
        }

        var outEdges = node.outgoers('edge');
        var inEdges = node.incomers('edge');
        var total = outEdges.length + inEdges.length;

        if (total > 0) {
            h += '<div class="p-section"><div class="p-label">Connections (' + total + ')</div>';
            outEdges.forEach(function (e) { h += connCard(e.target(), e.data('verb'), '\u2192'); });
            inEdges.forEach(function (e) { h += connCard(e.source(), e.data('verb'), '\u2190'); });
            h += '</div>';
        }

        openPanel(h);
        bindClicks();
    }

    function connCard(node, verb, arrow) {
        var d = node.data();
        var color = COLORS[d.type] || '#666';
        var bc = 'b-' + (d.status || 'active');
        var preview = (d.content || '').replace(/^##?\s.+\n*/gm, '').replace(/\*\*/g, '').trim().slice(0, 100);

        return '<div class="conn" data-id="' + d.id + '">' +
            '<div class="conn-head">' +
                '<span class="dot" style="background:' + color + '"></span>' +
                '<span class="conn-name">' + (d.title || d.id) + '</span>' +
                '<span class="badge ' + bc + '">' + (d.status || '?') + '</span>' +
            '</div>' +
            '<div class="conn-verb">' + arrow + ' ' + verb + '</div>' +
            (preview ? '<div class="conn-desc">' + preview + '</div>' : '') +
        '</div>';
    }

    function showEdge(edge) {
        var d = edge.data();
        var h = '<div class="p-header">';
        h += '<div class="p-type">relationship</div>';
        h += '<div class="p-title">' + d.verb + '</div>';
        h += '<div class="p-meta"><span class="badge ' + (d.active ? 'b-active' : 'b-archived') + '">' + (d.active ? 'active' : 'ended') + '</span></div>';
        h += '</div>';
        h += '<div class="p-section"><div class="p-label">From</div>' + connCard(edge.source(), '', '') + '</div>';
        h += '<div class="p-section"><div class="p-label">To</div>' + connCard(edge.target(), '', '') + '</div>';
        openPanel(h);
        bindClicks();
    }

    function bindClicks() {
        var cards = document.querySelectorAll('#panel-body .conn');
        for (var i = 0; i < cards.length; i++) {
            cards[i].addEventListener('click', function () {
                var n = cy.getElementById(this.dataset.id);
                if (n.length) {
                    cy.animate({ center: { eles: n }, zoom: 2 }, { duration: 250 });
                    showNode(n);
                }
            });
        }
    }

    // ---- Context menu ----
    function showCtx(x, y) {
        var m = document.getElementById('ctx');
        m.style.left = x + 'px';
        m.style.top = y + 'px';
        m.classList.remove('closed');
    }
    function hideCtx() { document.getElementById('ctx').classList.add('closed'); }

    var DEP = ['depends on', 'cannot start until', 'blocked by', 'requires'];

    function highlightChain(id) {
        cy.elements().addClass('dimmed');
        var root = cy.getElementById(id);
        root.removeClass('dimmed').addClass('highlighted');
        var frontier = root.outgoers('edge').filter(function (e) { return DEP.indexOf(e.data('verb')) !== -1; });
        var visited = {};
        visited[id] = true;
        while (frontier.length > 0) {
            frontier.removeClass('dimmed');
            var tgts = frontier.targets();
            tgts.forEach(function (t) { if (!visited[t.id()]) { visited[t.id()] = true; t.removeClass('dimmed'); } });
            frontier = tgts.outgoers('edge').filter(function (e) { return DEP.indexOf(e.data('verb')) !== -1 && !visited[e.target().id()]; });
        }
    }

    function highlightBlast(id, hops) {
        cy.elements().addClass('dimmed');
        var a = cy.getElementById(id);
        a.removeClass('dimmed').addClass('highlighted');
        var cur = a.closedNeighborhood();
        cur.removeClass('dimmed');
        for (var i = 1; i < hops; i++) { cur = cur.closedNeighborhood(); cur.removeClass('dimmed'); }
    }

    function resetView() { cy.elements().removeClass('dimmed').removeClass('highlighted'); }

    // ---- Filters ----
    function setupFilters() {
        var tc = document.getElementById('type-filters');
        var types = {};
        cy.nodes().forEach(function (n) { if (n.data('type')) types[n.data('type')] = true; });
        Object.keys(types).sort().forEach(function (type) {
            var l = document.createElement('label');
            l.className = 'f-item';
            l.innerHTML = '<input type="checkbox" checked data-type="' + type + '"><span class="f-dot" style="background:' + (COLORS[type] || '#666') + '"></span>' + type;
            l.querySelector('input').addEventListener('change', applyFilters);
            tc.appendChild(l);
        });

        var sc = document.getElementById('status-filters');
        var statuses = {};
        cy.nodes().forEach(function (n) { if (n.data('status')) statuses[n.data('status')] = true; });
        Object.keys(statuses).sort().forEach(function (st) {
            var l = document.createElement('label');
            l.className = 'f-item';
            l.innerHTML = '<input type="checkbox" checked data-status="' + st + '">' + st;
            l.querySelector('input').addEventListener('change', applyFilters);
            sc.appendChild(l);
        });
    }

    function applyFilters() {
        var types = {};
        document.querySelectorAll('#type-filters input:checked').forEach(function (c) { types[c.dataset.type] = true; });
        var statuses = {};
        document.querySelectorAll('#status-filters input:checked').forEach(function (c) { statuses[c.dataset.status] = true; });
        var ao = document.getElementById('active-only').checked;
        var sm = parseInt(document.getElementById('staleness-slider').value);

        cy.nodes().forEach(function (n) {
            var vis = true;
            if (n.data('type') && !types[n.data('type')]) vis = false;
            if (n.data('status') && !statuses[n.data('status')]) vis = false;
            if (ao && n.data('status') && ['active','in_progress','pending','blocked'].indexOf(n.data('status')) === -1) vis = false;
            if (sm < 90 && n.data('freshness_days') != null && n.data('freshness_days') > sm) vis = false;
            n.style('display', vis ? 'element' : 'none');
        });
        cy.edges().forEach(function (e) {
            e.style('display', (e.source().style('display') !== 'none' && e.target().style('display') !== 'none') ? 'element' : 'none');
        });
    }

    // ---- Init ----
    function init(data) {
        cy = cytoscape({
            container: document.getElementById('cy'),
            elements: data.elements,
            style: stylesheet(),
            layout: { name: 'preset' }, // positions set by hubClusterLayout
            minZoom: 0.1,
            maxZoom: 5,
        });

        // Run custom hub-cluster layout
        hubClusterLayout();
        cy.fit(undefined, 40);

        cy.on('tap', 'node', function (e) { showNode(e.target); });
        cy.on('tap', 'edge', function (e) { showEdge(e.target); });
        cy.on('tap', function (e) { if (e.target === cy) { hideCtx(); closePanel(); } });
        cy.on('cxttap', 'node', function (e) {
            e.originalEvent.preventDefault();
            selectedNode = e.target;
            showCtx(e.originalEvent.clientX, e.originalEvent.clientY);
        });

        document.getElementById('search').addEventListener('input', function (e) {
            var q = e.target.value.toLowerCase();
            if (!q) { resetView(); return; }
            cy.elements().addClass('dimmed');
            cy.nodes().forEach(function (n) {
                if ((n.data('title') || '').toLowerCase().indexOf(q) !== -1
                    || (n.data('id') || '').toLowerCase().indexOf(q) !== -1
                    || (n.data('type') || '').toLowerCase().indexOf(q) !== -1) {
                    n.removeClass('dimmed');
                    n.connectedEdges().removeClass('dimmed');
                    n.neighborhood('node').removeClass('dimmed');
                }
            });
        });

        document.getElementById('active-only').addEventListener('change', applyFilters);
        document.getElementById('staleness-slider').addEventListener('input', function (e) {
            document.getElementById('staleness-label').textContent = parseInt(e.target.value) >= 90 ? 'All' : '< ' + e.target.value + 'd';
            applyFilters();
        });

        var pills = document.querySelectorAll('.pill');
        for (var i = 0; i < pills.length; i++) {
            pills[i].addEventListener('click', function () {
                document.querySelectorAll('.pill').forEach(function (x) { x.classList.remove('active'); });
                this.classList.add('active');
                var name = this.dataset.layout;
                if (name === 'cluster') {
                    hubClusterLayout();
                    cy.fit(undefined, 40);
                } else {
                    var opts = { name: name, animate: true, animationDuration: 600 };
                    if (name === 'cose') {
                        opts.nodeRepulsion = function (node) { var sz = SIZES[node.data('type')] || 18; return sz * sz * 15; };
                        opts.idealEdgeLength = function () { return 180; };
                        opts.gravity = 0.15;
                        opts.numIter = 800;
                        opts.padding = 60;
                    }
                    if (name === 'breadthfirst') { opts.directed = true; opts.spacingFactor = 1.3; }
                    cy.layout(opts).run();
                }
            });
        }

        var ctxItems = document.querySelectorAll('.ctx-item');
        for (var j = 0; j < ctxItems.length; j++) {
            ctxItems[j].addEventListener('click', function () {
                hideCtx();
                if (this.dataset.action === 'chain' && selectedNode) highlightChain(selectedNode.id());
                if (this.dataset.action === 'blast' && selectedNode) highlightBlast(selectedNode.id(), 3);
                if (this.dataset.action === 'reset') resetView();
            });
        }

        document.getElementById('panel-close').addEventListener('click', closePanel);
        document.addEventListener('click', function (e) { if (!e.target.closest('#ctx')) hideCtx(); });

        setupFilters();

        // Default to active only
        document.getElementById('active-only').checked = true;
        applyFilters();

        var m = data.meta || {};
        document.getElementById('meta').textContent = (m.node_count || 0) + ' nodes \u00b7 ' + (m.edge_count || 0) + ' edges';
    }

    var lastNodeCount = 0;

    function loadGraph() {
        fetch('../exports/graph.json?t=' + Date.now())
            .then(function (r) { if (!r.ok) throw new Error('No data'); return r.json(); })
            .then(function (data) {
                var newCount = (data.meta || {}).node_count || 0;
                if (!cy) {
                    init(data);
                    lastNodeCount = newCount;
                } else if (newCount !== lastNodeCount) {
                    // Data changed -- reload
                    lastNodeCount = newCount;
                    cy.destroy();
                    cy = null;
                    document.getElementById('type-filters').innerHTML = '';
                    document.getElementById('status-filters').innerHTML = '';
                    init(data);
                }
            })
            .catch(function (err) {
                if (!cy) {
                    document.getElementById('cy').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#777">' + err.message + '</div>';
                }
            });
    }

    // Initial load
    loadGraph();

    // Auto-refresh every 5 minutes (picks up new exports without manual reload)
    setInterval(loadGraph, 5 * 60 * 1000);
})();
