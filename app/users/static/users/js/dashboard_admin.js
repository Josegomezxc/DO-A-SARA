/* =====================================================
   dashboard_admin.js
   Renderiza los gráficos del dashboard del administrador
   usando Chart.js. Los datos vienen serializados como JSON
   en un <script type="application/json" id="dashboard-chart-data">.
===================================================== */
(function () {
  'use strict';

  if (typeof Chart === 'undefined') {
    console.warn('Chart.js no está cargado.');
    return;
  }

  // -------- Leer datos del HTML --------
  let data;
  try {
    data = JSON.parse(document.getElementById('dashboard-chart-data').textContent);
  } catch (e) {
    console.error('No se pudieron parsear los datos de los gráficos', e);
    return;
  }

  const BRAND = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#2563EB';
  const BRAND_LIGHT = getComputedStyle(document.documentElement).getPropertyValue('--brand-light').trim() || '#EFF6FF';
  const BRAND_DEEP = getComputedStyle(document.documentElement).getPropertyValue('--brand-deep').trim() || '#1E3A8A';

  // -------- Gráfico 1: Ventas por día (línea) --------
  const $linea = document.getElementById('chart-ventas-dias');
  if ($linea && data.dias) {
    new Chart($linea, {
      type: 'line',
      data: {
        labels: data.dias.labels,
        datasets: [{
          label: 'Ventas ($)',
          data: data.dias.data,
          fill: true,
          backgroundColor: 'rgba(37, 99, 235, 0.15)',
          borderColor: BRAND,
          borderWidth: 2.5,
          pointBackgroundColor: BRAND,
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointRadius: 5,
          pointHoverRadius: 7,
          lineTension: 0.35,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        legend: { display: false },
        scales: {
          yAxes: [{
            ticks: {
              beginAtZero: true,
              callback: (value) => '$' + value.toLocaleString('es-AR'),
            },
            gridLines: { color: '#eaecf4', zeroLineColor: '#eaecf4', drawBorder: false },
          }],
          xAxes: [{
            gridLines: { display: false, drawBorder: false },
          }],
        },
        tooltips: {
          backgroundColor: BRAND_DEEP,
          titleFontColor: '#fff',
          bodyFontColor: '#fff',
          callbacks: {
            label: (item) => '$' + Number(item.yLabel).toLocaleString('es-AR', { minimumFractionDigits: 2 }),
          },
        },
      },
    });
  }

  // -------- Gráfico 2: Ventas por categoría (doughnut) --------
  const $cat = document.getElementById('chart-ventas-categorias');
  if ($cat && data.categorias && data.categorias.labels.length) {
    new Chart($cat, {
      type: 'doughnut',
      data: {
        labels: data.categorias.labels,
        datasets: [{
          data: data.categorias.data,
          backgroundColor: data.categorias.colors,
          borderColor: '#fff',
          borderWidth: 2,
          hoverBorderWidth: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutoutPercentage: 60,
        legend: {
          position: 'bottom',
          labels: { boxWidth: 14, fontSize: 12, padding: 12 },
        },
        tooltips: {
          backgroundColor: BRAND_DEEP,
          titleFontColor: '#fff',
          bodyFontColor: '#fff',
          callbacks: {
            label: (item, d) => {
              const label = d.labels[item.index] || '';
              const value = d.datasets[0].data[item.index];
              return ' ' + label + ': $' + Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2 });
            },
          },
        },
      },
    });
  }
})();
