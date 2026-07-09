const API_URL = localStorage.getItem("apiUrl") || "http://localhost:8000";

const questionForm = document.getElementById("questionForm");
const questionInput = document.getElementById("questionInput");
const submitBtn = document.getElementById("submitBtn");
const errorContainer = document.getElementById("errorContainer");
const errorMessage = document.getElementById("errorMessage");
const loadingContainer = document.getElementById("loadingContainer");
const responseContainer = document.getElementById("responseContainer");
const emptyState = document.getElementById("emptyState");

questionForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();

  if (!question) return;

  await askQuestion(question);
});

async function askQuestion(question) {
  submitBtn.disabled = true;
  loadingContainer.classList.remove("hidden");
  errorContainer.classList.add("hidden");
  responseContainer.classList.add("hidden");
  emptyState.classList.add("hidden");

  try {
    const response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Une erreur est survenue");
    }

    const data = await response.json();
    displayResponse(data);
  } catch (error) {
    showError(error.message || "Une erreur inattendue est survenue");
  } finally {
    submitBtn.disabled = false;
    loadingContainer.classList.add("hidden");
  }
}

function displayResponse(data) {
  // Response text
  document.getElementById("responseText").textContent = data.response;

  // Moderation status
  const modContainer = document.getElementById("moderationContainer");
  const modStatus = document.getElementById("moderationStatus");
  const modReason = document.getElementById("moderationReason");

  if (data.moderation.safe) {
    modContainer.classList.add("bg-green-50", "border", "border-green-200");
    modContainer.classList.remove("bg-red-50", "border-red-200");
    modStatus.classList.add("text-green-800");
    modStatus.classList.remove("text-red-800");
    modStatus.textContent = "Statut de modération: ✓ Sûr";
  } else {
    modContainer.classList.add("bg-red-50", "border", "border-red-200");
    modContainer.classList.remove("bg-green-50", "border-green-200");
    modStatus.classList.add("text-red-800");
    modStatus.classList.remove("text-green-800");
    modStatus.textContent = "Statut de modération: ✗ Bloqué";
  }

  if (data.moderation.reason) {
    modReason.textContent = data.moderation.reason;
    modReason.classList.add(data.moderation.safe ? "text-green-600" : "text-red-600");
  }

  // Source documents
  const sourceTitle = document.getElementById("sourceTitle");
  sourceTitle.textContent = `Sources (${data.documents.length})`;

  const documentsContainer = document.getElementById("documentsContainer");
  documentsContainer.innerHTML = "";

  data.documents.forEach((doc, idx) => {
    const metadata = data.metadatas[idx];
    const similarity = metadata.similarity
      ? (metadata.similarity * 100).toFixed(1)
      : "N/A";

    const docElement = document.createElement("div");
    docElement.className = "border-l-4 border-blue-500 pl-4 py-2";
    docElement.innerHTML = `
      <div class="flex justify-between items-start mb-2">
        <div>
          <p class="font-semibold text-gray-900">${metadata.num}</p>
          <p class="text-sm text-gray-500">${metadata.section_path}</p>
        </div>
        <span class="text-sm font-semibold text-blue-600">${similarity}%</span>
      </div>
      <p class="text-gray-700 text-sm leading-relaxed">${doc}</p>
    `;
    documentsContainer.appendChild(docElement);
  });

  responseContainer.classList.remove("hidden");
}

function showError(message) {
  errorMessage.textContent = message;
  errorContainer.classList.remove("hidden");
}

// Allow changing API URL from browser console
window.setApiUrl = function (url) {
  localStorage.setItem("apiUrl", url);
  console.log(`API URL set to: ${url}`);
};

console.log(`Using API URL: ${API_URL}`);
console.log(`To change: window.setApiUrl("http://your-url:8000")`);
