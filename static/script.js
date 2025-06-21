/* static/script.js
   ───────────────────────────────────────────────────────────
   Загружает метрики из /api/metrics и строит пять графиков
   c помощью Chart.js 4.

   Файл рассчитан на работу внутри index_front.html.
*/

// Цвета, привязанные к группам
const groupColors = {
    'CF':    '#4dd143',
    'Fixed': '#d1b243',
    'KB':    '#d15843'
};

// Активны ли группы (для чекбоксов слева)
const activeGroups = { CF: true, Fixed: true, KB: true };

// Все данные, пришедшие из бэкенда, складываем сюда
let groupData = {};

// Все экземпляры графиков Chart.js будем хранить здесь,
// чтобы потом легко обновлять
const charts = {};


/* --------------------------------------------------------------
 *  Шаг 1. Дожидаемся полной загрузки страницы,
 *         потом тянем JSON с сервера и строим графики.
 * ------------------------------------------------------------*/
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/metrics')
        .then(resp => resp.json())
        .then(json => {
            // Преобразуем список объектов в словарь {CF: {...}, Fixed: {...}, …}
            json.forEach(row => {
                const key = normaliseGroup(row.recommendation_method);
                groupData[key] = {
                    // Для бар-чартов нужен единственный элемент,
                    // a для line-чартов продублируем одно и то же значение,
                    // чтобы получилась «прямая линия».
                    group_size:       [row.group_size],
                    retention:        Array(5).fill(row.retention),
                    engagement:       Array(5).fill(row.engagement),
                    mastery_rate:     [row.mastery_rate],
                    mastery_trajectory: Array(5).fill(row.mastery_rate) // временно та же величина
                };
            });

            // После подготовки данных инициализируем графики
            initCharts();
            setupEventListeners();
        })
        .catch(err => console.error('Не удалось загрузить /api/metrics:', err));
});


/* --------------------------------------------------------------
 *   Шаг 2. Вспомогательные функции
 * ------------------------------------------------------------*/

// Приводим 'cf' / 'CF' → 'CF', 'kb' → 'KB' и т. д.
function normaliseGroup(method) {
    const m = method.toLowerCase();
    if (m === 'cf')    return 'CF';
    if (m === 'fixed') return 'Fixed';
    if (m === 'kb')    return 'KB';
    return method; // fallback
}

// Генерация наборов данных для каждого графика
function getGroupDatasets(metricKey) {
    const datasets = [];

    Object.keys(activeGroups).forEach(groupName => {
        if (activeGroups[groupName] && groupData[groupName]) {
            datasets.push({
                label: groupName,
                data:  groupData[groupName][metricKey],
                borderWidth: 3,
                backgroundColor: groupColors[groupName],
                borderColor:     groupColors[groupName]
            });
        }
    });

    return datasets;
}

// Единые опции для всех графиков
function chartOptions(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
        plugins: {
            legend: { position: 'top' },
            title:  { display: true, text: title, font: { size: 16 } }
        }
    };
}


/* --------------------------------------------------------------
 *   Шаг 3. Построение графиков
 * ------------------------------------------------------------*/
function initCharts() {
    // 1. Group size (bar)
    charts.size = new Chart(
        document.getElementById('chart-1'),
        {
            type: 'bar',
            data: { labels: [' '], datasets: getGroupDatasets('group_size') },
            options: chartOptions('Group Size')
        }
    );

    // 2. Retention (line)
    charts.retention = new Chart(
        document.getElementById('chart-2'),
        {
            type: 'line',
            data: { labels: ['', '', '', '', ''], datasets: getGroupDatasets('retention') },
            options: chartOptions('Retention (average launches)')
        }
    );

    // 3. Engagement (line)
    charts.engagement = new Chart(
        document.getElementById('chart-3'),
        {
            type: 'line',
            data: { labels: ['', '', '', '', ''], datasets: getGroupDatasets('engagement') },
            options: chartOptions('Engagement (log records)')
        }
    );

    // 4. Mastery rate (bar)
    charts.masteryRate = new Chart(
        document.getElementById('chart-4'),
        {
            type: 'bar',
            data: { labels: [' '], datasets: getGroupDatasets('mastery_rate') },
            options: chartOptions('Mastery Rate')
        }
    );

    // 5. Mastery trajectory (line, пока заглушка)
    charts.masteryTrajectory = new Chart(
        document.getElementById('chart-5'),
        {
            type: 'line',
            data: { labels: ['', '', '', '', ''], datasets: getGroupDatasets('mastery_trajectory') },
            options: chartOptions('Mastery Trajectory (placeholder)')
        }
    );
}


/* --------------------------------------------------------------
 *   Шаг 4. Переключатели групп (чекбоксы слева)
 * ------------------------------------------------------------*/
function setupEventListeners() {
    // Кнопки-чекбоксы CF / Fixed / KB
    document.querySelectorAll('.what-to-display-button').forEach(btn => {
        btn.addEventListener('click', () => {
            const group = btn.getAttribute('data-group');
            activeGroups[group] = !activeGroups[group];
            btn.classList.toggle('active', activeGroups[group]);
            updateAllCharts();
        });
    });

    // Выпадающее меню «Группы»
    document.getElementById('groups-button')
            .addEventListener('click', toggleMenu);
}

// Показ / скрытие выпадающего меню
function toggleMenu() {
    const menu = document.getElementById('what-to-display-menu');
    const isClosed = !menu.style.maxHeight || menu.style.maxHeight === '0px';
    menu.style.maxHeight = isClosed ? '200px' : '0';
    menu.style.padding   = isClosed ? '5px 0' : '0';
}

// Обновление всех графиков после изменения activeGroups
function updateAllCharts() {
    charts.size.data.datasets           = getGroupDatasets('group_size');
    charts.retention.data.datasets      = getGroupDatasets('retention');
    charts.engagement.data.datasets     = getGroupDatasets('engagement');
    charts.masteryRate.data.datasets    = getGroupDatasets('mastery_rate');
    charts.masteryTrajectory.data.datasets = getGroupDatasets('mastery_trajectory');

    // Chart.js 4 требует вызвать update() у каждого графика
    Object.values(charts).forEach(ch => ch.update());
}
