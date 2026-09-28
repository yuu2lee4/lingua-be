import ky from "ky";

export const api = ky.create({
  prefixUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  timeout: 60000,
  hooks: {
    beforeError: [
      async (error) => {
        const { response } = error;
        if (response) {
          try {
            const body = await response.json();
            error.message = (body as { detail?: string }).detail || error.message;
          } catch {
            // ignore json parse errors
          }
        }
        return error;
      },
    ],
  },
});
