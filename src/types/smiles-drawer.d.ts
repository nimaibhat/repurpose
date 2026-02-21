declare module 'smiles-drawer' {
  const SmilesDrawer: {
    Drawer: new (options?: any) => {
      draw: (tree: any, canvas: HTMLCanvasElement, theme?: string) => void;
    };
    parse: (smiles: string, callback: (tree: any) => void, errorCallback?: (err: any) => void) => void;
  };
  export default SmilesDrawer;
}
