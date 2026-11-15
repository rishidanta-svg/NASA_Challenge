import { Component, type ReactNode } from 'react';

/** A graphics failure must not take the evidence tools down with it. */
export class MapBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true}}
  render(){return this.state.failed?<div className="map-fallback" role="status"><h2>The map could not start</h2><p>Your browser may not support WebGL. Study findings, survey profiles and downloads are still available from Explore.</p><button onClick={()=>this.setState({failed:false})}>Try the map again</button></div>:this.props.children}
}
