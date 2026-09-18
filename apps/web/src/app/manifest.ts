import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'EasyDentist',
    short_name: 'EasyDentist',
    description: 'Gestão segura de clínicas odontológicas',
    start_url: '/clinics',
    display: 'standalone',
    background_color: '#f4f8f9',
    theme_color: '#0d3b47',
    lang: 'pt-BR',
    icons: [
      {
        src: '/icons/easydentist-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/icons/easydentist-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icons/easydentist-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
