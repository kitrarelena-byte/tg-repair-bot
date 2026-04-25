async function addReport() {
    await fetch("/report", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            model: document.getElementById("model").value,
            repair_price: parseFloat(document.getElementById("repair").value),
            sell_price: parseFloat(document.getElementById("sell").value)
        })
    });

    alert("Добавлено");
}

async function addPart() {
    await fetch("/part", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name: document.getElementById("partName").value,
            price: parseFloat(document.getElementById("partPrice").value)
        })
    });

    alert("Запчасть добавлена");
}