// // Validate finished QTY before submission
// frappe.ui.form.on("Job Card", {
// 	validate: function(frm) {
//     	if (frm.doc.status === "Completed") {
//         	if (frm.doc.total_completed_qty !== frm.doc.total_qty) {
//             	frappe.throw(`Completed quantity (${frm.doc.total_completed_qty}) must match the total quantity (${frm.doc.total_qty}) before completing this job.`);
//         	}
//     	}
// 	}
// });

// // Create Petty Cash Request
// frappe.ui.form.on('Job Card', {
// 	refresh: function(frm) {
// 	  // Petty Cash Request under the Create menu
// 	  frm.add_custom_button(__('Petty Cash Request'), () => {
// 		frappe.new_doc('Petty Cash Request', {
// 		  job_card: frm.doc.name
// 		});
// 	  }, __('Create'));
  
// 	  // Damages and Returns under the Create menu
// 	  frm.add_custom_button(__('Damages and Returns'), () => {
// 		frappe.new_doc('Damages and Returns', {
// 		  job_card: frm.doc.name
// 		});
// 	  }, __('Create'));

// 	   // Damages and Returns under the Create menu
// 	   frm.add_custom_button(__('Withdrawal Slip'), () => {
// 		frappe.new_doc('Material Request', {
// 		  stock_entry_type: "Material Transfer for Manufacture"
// 		});
// 	  });

// 	}
//   });
  

// Create Petty Cash Request
frappe.ui.form.on('Job Card', {
	refresh: function(frm) {
	  // Petty Cash Request under the Create menu
	  frm.add_custom_button(__('Material Request'), () => {
		frappe.new_doc('Material Request', {
		  job_card: frm.doc.name,
		  work_order: frm.doc.work_order,
		  material_request_type: 'Material Transfer',
		  set_warehouse: 'Work In Progress - CM CDO',
		  
		});
	  }, __('Create'));
	}
  });
  