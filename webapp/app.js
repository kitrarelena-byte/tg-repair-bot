async function load() {
    const user = Telegram.WebApp.initDataUnsafe.user.id;

    const res = await fetch(`/analytics/${user}`);
    const data = await res.json();

    new Chart(document.getElementById("chart"), {
        type: "bar",
        data: {
            labels: ["Прибыль"],
            datasets: [{
                label: "₽",
                data: [data.total]
            }]
        }
    });
}

load();