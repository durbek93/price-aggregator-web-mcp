// Helper function to parse process progress from logs
export const parseProgressFromLogs = (progressMessage) => {
  if (!progressMessage) return null;
  const parts = progressMessage.split(' ||| ');
  let maxPercent = null;
  const regex = /Обработка\s*\[(\d+)\/(\d+)\]/;
  for (const part of parts) {
    const match = part.match(regex);
    if (match) {
      const current = parseInt(match[1], 10);
      const total = parseInt(match[2], 10);
      if (total > 0) {
        const percent = Math.round((current / total) * 95); // limit to 95% until complete
        if (maxPercent === null || percent > maxPercent) {
          maxPercent = percent;
        }
      }
    }
  }
  return maxPercent;
};

// Helper function to format time (seconds -> mm:ss)
export const formatTime = (seconds) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
};
