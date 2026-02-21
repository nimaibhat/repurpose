declare module '3dmol' {
  export enum SurfaceType {
    VDW = 1,
    MS = 2,
    SAS = 3,
    SES = 4,
  }

  export function createViewer(
    element: HTMLElement,
    config?: {
      backgroundColor?: string;
      antialias?: boolean;
      id?: string;
    },
  ): GLViewer;

  export interface GLViewer {
    addModel(data: string, format: string): GLModel;
    setStyle(sel: object, style: object): void;
    addSurface(type: SurfaceType, style?: object, sel?: object): any;
    removeSurface(surfaceId: any): void;
    removeAllSurfaces(): void;
    zoomTo(sel?: object): void;
    render(): void;
    spin(axis: string | boolean, speed?: number): void;
    clear(): void;
    removeModel(model: GLModel): void;
    removeAllModels(): void;
    resize(): void;
    getModel(index?: number): GLModel;
    setViewStyle(style: object): void;
  }

  export interface GLModel {
    setStyle(sel: object, style: object): void;
    removeAtoms(sel: object): void;
  }
}
