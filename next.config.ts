import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  transpilePackages: ['three', 'ogl', '3dmol', 'smiles-drawer'],
};

export default nextConfig;
