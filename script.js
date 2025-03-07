// Filtres
function filterByDate() {
    let startDate = document.getElementById("startDate").value;
    let endDate = document.getElementById("endDate").value;
    // Appliquer le filtre sur les données du tableau
  }
  
  function searchTrade() {
    let searchQuery = document.getElementById("search").value.toLowerCase();
    let rows = document.querySelectorAll(".record-table tbody tr");
    
    rows.forEach(row => {
      let cells = row.querySelectorAll("td");
      let match = false;
      
      cells.forEach(cell => {
        if (cell.textContent.toLowerCase().includes(searchQuery)) {
          match = true;
        }
      });
  
      row.style.display = match ? "" : "none";
    });
  }
  
  function resetFilters() {
    document.getElementById("search").value = '';
    document.getElementById("startDate").value = '';
    document.getElementById("endDate").value = '';
    // Réinitialiser le tableau
  }
  
  // Calcul des gains en pips et en pourcentage
  function calculatePips(entry, exit) {
    return (exit - entry) * 10000;  // Exemple pour EUR/USD
  }
  
  function calculatePercentage(entry, exit) {
    return ((exit - entry) / entry) * 100;
  }
  
  // Exemple de données pour tester
  const trades = [
    { date: '2025-03-01', pair: 'EUR/USD', type: 'long', entry: 1.1000, exit: 1.1050, lot: 1.0, comment: 'Trade basé sur la tendance haussière' },
    { date: '2025-03-02', pair: 'GBP/USD', type: 'short', entry: 1.2000, exit: 1.1950, lot: 0.5, comment: 'Correction technique' }
  ];
  
  function displayTrades() {
    const tbody = document.querySelector('.record-table tbody');
    tbody.innerHTML = ''; // Clear existing rows
    trades.forEach(trade => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${trade.date}</td>
        <td>${trade.pair}</td>
        <td>${trade.type}</td>
        <td>${trade.lot}</td>
        <td>${trade.entry}</td>
        <td>${trade.exit}</td>
        <td>${calculatePips(trade.entry, trade.exit)}</td>
        <td>${calculatePercentage(trade.entry, trade.exit)}%</td>
        <td>${trade.comment}</td>
      `;
      tbody.appendChild(row);
    });
  }
  
  // Afficher les statistiques de performance
  function displayStats() {
    let totalTrades = trades.length;
    let successfulTrades = trades.filter(trade => calculatePercentage(trade.entry, trade.exit) > 0).length;
    let successRate = (successfulTrades / totalTrades) * 100;
    
    document.getElementById("success-rate").textContent = `${successRate.toFixed(2)}%`;
  
    // Ajouter un calcul du ratio de Sharpe si tu le souhaites ici
  }
  
  // Générer le graphique de performance
  function generatePerformanceChart() {
    const ctx = document.getElementById('performanceChart').getContext('2d');
    const performanceData = trades.map(trade => calculatePercentage(trade.entry, trade.exit));
    
    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: trades.map(trade => trade.date),
        datasets: [{
          label: 'Performance (%)',
          data: performanceData,
          borderColor: '#00ffcc',
          fill: false,
        }]
      }
    });
  }
  
  // Fonction de téléchargement CSV
  function downloadCSV() {
    let csv = 'Date,Pair,Type,Taille du lot,Entrée,Sortie,Gain/Perte (pips),Gain/Perte (%),Commentaires\n';
    trades.forEach(trade => {
      csv += `${trade.date},${trade.pair},${trade.type},${trade.lot},${trade.entry},${trade.exit},${calculatePips(trade.entry, trade.exit)},${calculatePercentage(trade.entry, trade.exit)},${trade.comment}\n`;
    });
    const link = document.createElement('a');
    link.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    link.download = 'track-record.csv';
    link.click();
  }
  
  // Télécharger en PDF
  function downloadPDF() {
    const doc = new jsPDF();
    doc.text("Track Record", 10, 10);
    trades.forEach((trade, index) => {
      doc.text(`${trade.date} | ${trade.pair} | ${trade.type} | Gain/Perte: ${calculatePercentage(trade.entry, trade.exit)}%`, 10, 20 + index * 10);
    });
    doc.save('track-record.pdf');
  }
  
  // Initialisation
  displayTrades();
  displayStats();
  generatePerformanceChart();
  